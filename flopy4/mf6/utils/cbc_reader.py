import os
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any, BinaryIO, cast

import dask
import dask.array
import numpy as np
import xarray as xr
import xugrid as xu
from attrs import define
from flopy.discretization import StructuredGrid

from flopy4.adapters import read_binary_grid_file
from flopy4.mf6.utils.grid import get_coords
from flopy4.mf6.utils.time import assign_datetime_coords


@define
class Imeth1Header:
    kstp: int
    kper: int
    text: str
    ndim1: int
    ndim2: int
    ndim3: int
    imeth: int
    delt: float
    pertim: float
    totim: float
    pos: int


@define
class Imeth6Header:
    kstp: int
    kper: int
    text: str
    ndim1: int
    ndim2: int
    ndim3: int
    imeth: int
    delt: float
    pertim: float
    totim: float
    pos: int
    txt1id1: str
    txt2id1: str
    txt1id2: str
    txt2id2: str
    ndat: int
    auxtxt: list[str]
    nlist: int


XUGRID_FILL_VALUE = -1
IDOMAIN_ACTIVE = 1


def open_cbc(
    cbc_path: Path,
    grb_path: Path,
    flowja: bool = False,
    simulation_start_time: np.datetime64 | None = None,
    time_unit: str | None = "d",
) -> xr.Dataset | xu.UgridDataset:
    """
    Open modflow6 cell-by-cell (.cbc) file.

    The data is lazily read per timestep and automatically converted into
    (dense) xr.DataArrays or xu.UgridDataArrays, for DIS and DISV respectively.
    The conversion is done via the information stored in the Binary Grid file
    (GRB).

    The ``flowja`` argument controls whether the flow-ja-face array
    (if present) is returned in grid form as "as is".
    By default ``flowja=False`` and the array is returned in "grid form",
    meaning:

        * DIS: in right, front, and lower face flow. All flows are placed in
          the cell.
        * DISV: in horizontal, horizontal-x, horizontal-y, and lower face flow.

    When ``flowja=True``, the flow-ja-face array is returned as it is found in
    the CBC file, with a flow for every cell to cell connection. Additionally,
    a ``connectivity`` DataArray is returned describing for every cell (n) its
    connected cells (m).

    Parameters
    ----------
    cbc_path: str, pathlib.Path
        Path to the cell-by-cell flows file
    grb_path: str, pathlib.Path
        Path to the binary grid file
    flowja: bool, default value: False
        Whether to return the flow-ja-face values "as is" (``True``) or in a
        grid form (``False``).
    simulation_start_time : Optional datetime
        The time and date corresponding to the beginning of the simulation.
        Use this to convert the time coordinates of the output array to
        calendar time/dates. time_unit must also be present if this argument is
        present.
    time_unit: Optional str
        The time unit MF6 is working in, in string representation.
        Only used if simulation_start_time was provided.
        Admissible values are:
        ns -> nanosecond
        ms -> microsecond
        s -> second
        m -> minute
        h -> hour
        d -> day
        w -> week
        Units "month" or "year" are not supported, as they do not represent
        unambiguous timedelta values durations.

    Returns
    -------
    cbc_content: xr.Dataset | Dict[str, xr.DataArray]
        DataArray contains float64 data of the budgets,
        with dimensions ("time", "layer", "y", "x") for DIS
        or ("time", "layer", face_dimension) for DISV.

    Examples
    --------

    Open a cbc file:

    >>> import flopy4.mf6.utils
    >>> cbc_content = open_cbc("budgets.cbc", "my-model.grb")

    Check the contents:

    >>> print(cbc_content.keys())

    Get the drainage budget, compute a time mean for the first layer:

    >>> drn_budget = cbc_content["drn"]
    >>> mean = drn_budget.sel(layer=1).mean("time")

    """
    grb_info = read_binary_grid_file(grb_path)

    if grb_info["grid_type"] == "DIS":
        cbc = _open_cbc_dis(cbc_path, grb_info["grid"], flowja, simulation_start_time, time_unit)
        return xr.merge([cbc], compat="override")
    elif grb_info["grid_type"] == "DISV":
        cbc = _open_cbc_disv(cbc_path, grb_info, flowja, simulation_start_time, time_unit)
        # Build xr.Dataset from dict, extracting underlying xr.DataArrays
        # and assigning proper names
        ds_vars = {}
        for key, val in cbc.items():
            if isinstance(val, xu.UgridDataArray):
                da = val.obj
                da.name = key
                ds_vars[key] = da
            else:
                if val.name is None:
                    val.name = key
                ds_vars[key] = val
        ds = xr.Dataset(ds_vars)
        return xu.UgridDataset(ds, grids=grb_info["grid"])
    else:
        raise ValueError(f"Unsupported grid type: {grb_info['grid_type']}")


def _open_cbc_dis(
    cbc_path: Path,
    grid: StructuredGrid,
    flowja: bool = False,
    simulation_start_time: np.datetime64 | None = None,
    time_unit: str | None = "d",
) -> dict[str, xr.DataArray]:
    headers = read_cbc_headers(cbc_path)
    indices = None
    header_advanced_package = get_first_header_advanced_package(headers)
    if header_advanced_package is not None:
        # For advanced packages the id2 column of variable gwf contains the MF6
        # ids. Get id's eager from first stress period.
        dtype = np.dtype(
            [("id1", np.int32), ("id2", np.int32), ("budget", np.float64)]
            + [(name, np.float64) for name in header_advanced_package.auxtxt]
        )
        table = read_imeth6_budgets(
            cbc_path,
            header_advanced_package.nlist,
            dtype,
            header_advanced_package.pos,
        )
        indices = table["id2"] - 1  # Convert to 0 based index
    cbc_content = {}
    for key, header_list in headers.items():
        # TODO: validate homogeneity of header_list, ndat consistent,
        # nlist consistent etc.
        if key == "flow-ja-face" and isinstance(header_list[0], Imeth1Header):
            if not all(isinstance(x, Imeth1Header) for x in header_list):
                raise TypeError(f"Mixed header types for key {key!r}")
            if flowja:
                flowjaface, nm = open_face_budgets_as_flowja(
                    cbc_path, cast(list[Imeth1Header], header_list), grid
                )
                cbc_content["flow-ja-face"] = flowjaface
                cbc_content["connectivity"] = nm
            else:
                right, front, lower = dis_open_face_budgets(
                    cbc_path,
                    grid,
                    cast(list[Imeth1Header], header_list),
                )
                cbc_content["flow-right-face"] = right
                cbc_content["flow-front-face"] = front
                cbc_content["flow-lower-face"] = lower
        else:
            if isinstance(header_list[0], Imeth1Header):
                if not all(isinstance(x, Imeth1Header) for x in header_list):
                    raise TypeError(f"Mixed header types for key {key!r}")
                cbc_content[key] = open_imeth1_budgets(
                    cbc_path, grid, cast(list[Imeth1Header], header_list)
                )
            elif isinstance(header_list[0], Imeth6Header):
                if not all(isinstance(x, Imeth6Header) for x in header_list):
                    raise TypeError(f"Mixed header types for key {key!r}")

                # for non cell flow budget terms,
                # use auxiliary variables as return value
                if header_list[0].text.startswith("data-"):
                    for return_variable in header_list[0].auxtxt:
                        key_aux = f"{header_list[0].txt2id1}-{return_variable}"
                        cbc_content[key_aux] = open_imeth6_budgets(
                            cbc_path,
                            grid,
                            cast(list[Imeth6Header], header_list),
                            return_variable,
                            indices=indices,
                        )
                else:
                    cbc_content[key] = open_imeth6_budgets(
                        cbc_path,
                        grid,
                        cast(list[Imeth6Header], header_list),
                        indices=indices,
                    )
    if simulation_start_time is not None:
        for cbc_name, cbc_array in cbc_content.items():
            cbc_content[cbc_name] = assign_datetime_coords(
                cbc_array, simulation_start_time, time_unit
            )

    return cbc_content


def _open_cbc_disv(
    cbc_path: Path,
    grb_info: dict[str, Any],
    flowja: bool = False,
    simulation_start_time: np.datetime64 | None = None,
    time_unit: str | None = "d",
) -> dict[str, xu.UgridDataArray | xr.DataArray]:
    headers = read_cbc_headers(cbc_path)
    indices = None
    header_advanced_package = get_first_header_advanced_package(headers)
    if header_advanced_package is not None:
        dtype = np.dtype(
            [("id1", np.int32), ("id2", np.int32), ("budget", np.float64)]
            + [(name, np.float64) for name in header_advanced_package.auxtxt]
        )
        table = read_imeth6_budgets(
            cbc_path,
            header_advanced_package.nlist,
            dtype,
            header_advanced_package.pos,
        )
        indices = table["id2"] - 1

    cbc_content: dict[str, xu.UgridDataArray | xr.DataArray] = {}
    for key, header_list in headers.items():
        if key == "flow-ja-face" and isinstance(header_list[0], Imeth1Header):
            if not all(isinstance(x, Imeth1Header) for x in header_list):
                raise TypeError(f"Mixed header types for key {key!r}")
            if flowja:
                flowjaface, nm = open_face_budgets_as_flowja(
                    cbc_path, cast(list[Imeth1Header], header_list), grb_info
                )
                cbc_content["flow-ja-face"] = flowjaface
                cbc_content["connectivity"] = nm
            else:
                horizontal, flow_x, flow_y, lower = disv_open_face_budgets(
                    cbc_path,
                    grb_info,
                    cast(list[Imeth1Header], header_list),
                )
                cbc_content["flow-horizontal-face"] = horizontal
                cbc_content["flow-horizontal-face-x"] = flow_x
                cbc_content["flow-horizontal-face-y"] = flow_y
                cbc_content["flow-lower-face"] = lower
        elif isinstance(header_list[0], Imeth1Header):
            if not all(isinstance(x, Imeth1Header) for x in header_list):
                raise TypeError(f"Mixed header types for key {key!r}")
            cbc_content[key] = disv_open_imeth1_budgets(
                cbc_path, grb_info, cast(list[Imeth1Header], header_list)
            )
        elif isinstance(header_list[0], Imeth6Header):
            if not all(isinstance(x, Imeth6Header) for x in header_list):
                raise TypeError(f"Mixed header types for key {key!r}")
            if header_list[0].text.startswith("data-"):
                for return_variable in header_list[0].auxtxt:
                    key_aux = f"{header_list[0].txt2id1}-{return_variable}"
                    cbc_content[key_aux] = disv_open_imeth6_budgets(
                        cbc_path,
                        grb_info,
                        cast(list[Imeth6Header], header_list),
                        return_variable,
                        indices=indices,
                    )
            else:
                cbc_content[key] = disv_open_imeth6_budgets(
                    cbc_path,
                    grb_info,
                    cast(list[Imeth6Header], header_list),
                    indices=indices,
                )

    if simulation_start_time is not None:
        for cbc_name, cbc_array in cbc_content.items():
            cbc_content[cbc_name] = assign_datetime_coords(
                cbc_array, simulation_start_time, time_unit
            )

    return cbc_content


# grid-independent functions


def get_first_header_advanced_package(
    headers: dict[str, list[Any]],
) -> Any:
    for key, header_list in headers.items():
        # multimodels have a gwf-gwf budget for flow-ja-face between domains
        if "flow-ja-face" not in key and "gwf_" in key:
            return header_list[0]
    return None


def read_cbc_headers(
    cbc_path: Path,
) -> dict[str, list[Imeth1Header | Imeth6Header]]:
    """
    Read all the header data from a cell-by-cell (.cbc) budget file.

    All budget data for a MODFLOW6 model is stored in a single file. This
    function collects all header data, as well as the starting byte position of
    the actual budget data.

    This function groups the headers per TEXT record (e.g. "flow-ja-face",
    "drn", etc.). The headers are stored as a list of named tuples.
    flow-ja-face, storage-ss, and storage-sy are written using IMETH=1, all
    others with IMETH=6.

    Parameters
    ----------
    cbc_path: str, pathlib.Path
        Path to the budget file.

    Returns
    -------
    headers: Dict[List[UnionImeth1Header, Imeth6Header]]
        Dictionary containing a list of headers per TEXT record in the budget
        file.
    """
    headers: dict[str, list[Imeth1Header | Imeth6Header]] = defaultdict(list)
    with open(cbc_path, "rb") as f:
        filesize = os.fstat(f.fileno()).st_size
        while f.tell() < filesize:
            header = read_common_cbc_header(f)
            if header["imeth"] == 1:
                # Multiply by -1 because ndim3 is stored as a negative for some
                # reason. (ndim3 is the integer size of the third dimension)
                datasize = (header["ndim1"] * header["ndim2"] * header["ndim3"] * -1) * 8
                header["pos"] = f.tell()
                key = header["text"]
                headers[key].append(Imeth1Header(**header))
            elif header["imeth"] == 6:
                imeth6_header = read_imeth6_header(f)
                datasize = imeth6_header["nlist"] * (8 + imeth6_header["ndat"] * 8)
                header["pos"] = f.tell()
                # key-format:
                # "package type"-"optional_package_variable"_"package name"
                # for river output: riv_sys1
                # for uzf output: uzf-gwrch_uzf_sys1
                key = header["text"] + "_" + imeth6_header["txt2id2"]
                # npf-key can be present multiple times in cases of saved
                # saturation + specific discharge
                if header["text"].startswith("data-"):
                    key = imeth6_header["txt2id2"] + "_" + header["text"].replace("data-", "")
                headers[key].append(Imeth6Header(**header, **imeth6_header))
            else:
                raise ValueError(
                    f"Invalid imeth value in CBC file {cbc_path}. "
                    f"Should be 1 or 6, received: {header['imeth']}."
                )
            # Skip the data
            f.seek(datasize, 1)
    return headers


def read_common_cbc_header(f: BinaryIO) -> dict[str, Any]:
    """
    Read the common part (shared by imeth=1 and imeth6) of a CBC header section
    """
    content = {}
    content["kstp"] = struct.unpack("i", f.read(4))[0]
    content["kper"] = struct.unpack("i", f.read(4))[0]
    content["text"] = f.read(16).decode("utf-8").strip().lower()
    content["ndim1"] = struct.unpack("i", f.read(4))[0]
    content["ndim2"] = struct.unpack("i", f.read(4))[0]
    content["ndim3"] = struct.unpack("i", f.read(4))[0]
    content["imeth"] = struct.unpack("i", f.read(4))[0]
    content["delt"] = struct.unpack("d", f.read(8))[0]
    content["pertim"] = struct.unpack("d", f.read(8))[0]
    content["totim"] = struct.unpack("d", f.read(8))[0]
    return content


def read_imeth6_header(f: BinaryIO) -> dict[str, Any]:
    """
    Read the imeth=6 specific data of a CBC header section.
    """
    content: dict[str, str | list[str]] = {}
    content["txt1id1"] = f.read(16).decode("utf-8").strip().lower()
    content["txt2id1"] = f.read(16).decode("utf-8").strip().lower()
    content["txt1id2"] = f.read(16).decode("utf-8").strip().lower()
    content["txt2id2"] = f.read(16).decode("utf-8").strip().lower()
    ndat = struct.unpack("i", f.read(4))[0]
    content["ndat"] = ndat
    content["auxtxt"] = [f.read(16).decode("utf-8").strip().lower() for _ in range(ndat - 1)]
    content["nlist"] = struct.unpack("i", f.read(4))[0]
    return content


# imeth=6 budget reading (grid-independent core)


def read_imeth6_budgets(cbc_path: Path, count: int, dtype: np.dtype, pos: int) -> Any:
    """
    Read the data for an imeth==6 budget section for a single timestep.

    Returns a numpy structured array containing:
    * id1: the model cell number
    * id2: the boundary condition index
    * budget: the budget terms
    * and assorted auxiliary columns, if present
    """
    with open(cbc_path, "rb") as f:
        f.seek(pos)
        table = np.fromfile(f, dtype, count)
    return table


def read_imeth6_budgets_dense(
    cbc_path: Path,
    count: int,
    dtype: np.dtype,
    pos: int,
    size: int,
    shape: tuple,
    return_variable: str,
    indices: np.ndarray | None,
) -> np.ndarray:
    """
    Read the data for an imeth==6 budget section.

    Allocates a dense array for the entire domain and fills in values
    from the sparse budget data.
    """
    out = np.full(size, np.nan, dtype=np.float64)
    table = read_imeth6_budgets(cbc_path, count, dtype, pos)
    if indices is None:
        indices = table["id1"] - 1  # Convert to 0 based index
    out[indices] = 0
    np.add.at(out, indices, table[return_variable])
    return out.reshape(shape)


# imeth=1 budget reading (grid-independent core)


def read_imeth1_budgets(cbc_path: Path, count: int, pos: int) -> np.ndarray:
    """
    Read the data for an imeth=1 budget section.
    """
    with open(cbc_path, "rb") as f:
        f.seek(pos)
        timestep_budgets = np.fromfile(f, np.float64, count)
    return timestep_budgets


def cbc_open_imeth1_budgets(cbc_path: Path, header_list: list[Imeth1Header]) -> xr.DataArray:
    """
    Open the data for an imeth==1 budget section. Data is read lazily per
    timestep. The cell data is not spatially labelled.

    Returns
    -------
    xr.DataArray with dims ("time", "linear_index")
    """
    dask_list = []
    time = np.empty(len(header_list), dtype=np.float64)
    for i, header in enumerate(header_list):
        time[i] = header.totim
        count = header.ndim1 * header.ndim2 * header.ndim3 * -1
        a = dask.delayed(read_imeth1_budgets)(cbc_path, count, header.pos)
        x = dask.array.from_delayed(a, shape=(count,), dtype=np.float64)
        dask_list.append(x)

    return xr.DataArray(
        data=dask.array.stack(dask_list, axis=0),
        coords={"time": time},
        dims=("time", "linear_index"),
        name=header_list[0].text,
    )


# DIS-specific budget functions


def open_imeth6_budgets(
    cbc_path: Path,
    grid: StructuredGrid,
    header_list: list[Imeth6Header],
    return_variable: str = "budget",
    indices: np.ndarray | None = None,
) -> xr.DataArray:
    """
    Open the data for an imeth==6 budget section (DIS).

    Returns
    -------
    xr.DataArray with dims ("time", "layer", "y", "x")
    """
    dtype = np.dtype(
        [("id1", np.int32), ("id2", np.int32), ("budget", np.float64)]
        + [(name, np.float64) for name in header_list[0].auxtxt]
    )
    shape = (grid.nlay, grid.nrow, grid.ncol)
    size = np.prod(shape)
    dask_list = []
    time = np.empty(len(header_list), dtype=np.float64)
    for i, header in enumerate(header_list):
        time[i] = header.totim
        a = dask.delayed(read_imeth6_budgets_dense)(
            cbc_path,
            header.nlist,
            dtype,
            header.pos,
            size,
            shape,
            return_variable,
            indices,
        )
        x = dask.array.from_delayed(a, shape=shape, dtype=np.float64)
        dask_list.append(x)

    daskarr = dask.array.stack(dask_list, axis=0)
    coords = get_coords(grid)
    coords["time"] = time
    name = header_list[0].text
    return xr.DataArray(daskarr, coords, ("time", "layer", "y", "x"), name=name)


def open_imeth1_budgets(
    cbc_path: Path,
    grid: StructuredGrid,
    header_list: list[Imeth1Header],
) -> xr.DataArray:
    """
    Open the data for an imeth==1 budget section (DIS). Data is read lazily per
    timestep.

    Returns
    -------
    xr.DataArray with dims ("time", "layer", "y", "x")
    """
    nlayer = grid.nlay
    nrow = grid.nrow
    ncol = grid.ncol
    budgets = cbc_open_imeth1_budgets(cbc_path, header_list)
    coords = get_coords(grid) | {"time": budgets["time"]}

    return xr.DataArray(
        data=budgets.data.reshape((budgets["time"].size, nlayer, nrow, ncol)),
        coords=coords,
        dims=("time", "layer", "y", "x"),
        name=budgets.name,
    )


def dis_open_face_budgets(
    cbc_path: Path,
    grid: StructuredGrid,
    header_list: list[Imeth1Header],
) -> tuple[xr.DataArray, xr.DataArray, xr.DataArray]:
    """
    Open the flow-ja-face, and extract right, front, and lower face flows.

    Returns
    -------
    right: xr.DataArray of floats with dims ("time", "layer", "y", "x")
    front: xr.DataArray of floats with dims ("time", "layer", "y", "x")
    lower: xr.DataArray of floats with dims ("time", "layer", "y", "x")
    """
    right_index, front_index, lower_index = dis_to_right_front_lower_indices(grid)
    budgets = cbc_open_imeth1_budgets(cbc_path, header_list)
    right = dis_extract_face_budgets(budgets, right_index)
    front = dis_extract_face_budgets(budgets, front_index)
    lower = dis_extract_face_budgets(budgets, lower_index)
    return right, front, lower


def dis_extract_face_budgets(budgets: xr.DataArray, index: xr.DataArray) -> xr.DataArray:
    """
    Grab right, front, or lower face flows from the flow-ja-face array.
    """
    coords = dict(index.coords)
    coords["time"] = budgets["time"]
    data = budgets.isel(linear_index=index.values.ravel()).data
    da = xr.DataArray(
        data=data.reshape((budgets["time"].size, *index.shape)),
        coords=coords,
        dims=("time", "layer", "y", "x"),
        name="flow-ja-face",
    )
    return da.where(index >= 0, other=0.0)


def dis_to_right_front_lower_indices(
    grid: StructuredGrid,
) -> tuple[xr.DataArray, xr.DataArray, xr.DataArray]:
    """
    Infer the indices to extract right, front, and lower face flows from the
    flow-ja-face array.
    """
    right, front, lower = dis_indices(grid)
    coords = get_coords(grid)
    return (
        xr.DataArray(right, coords, ("layer", "y", "x")),
        xr.DataArray(front, coords, ("layer", "y", "x")),
        xr.DataArray(lower, coords, ("layer", "y", "x")),
    )


def dis_indices(
    grid: StructuredGrid,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Infer type of connection via cell number comparison. Returns arrays
    that can be used for extracting right, front, and lower face flow from the
    flow-ja-face array.

    ``grid.ia`` and ``grid.ja`` must be 0-based CSR arrays (as returned by
    :class:`~flopy4.adapters.StructuredGridWrapper`, which reads them from the
    GRB file via ``MfGrdFile`` — which converts Fortran 1-based indices to
    0-based on read).  ``nzi`` is a direct index into ``ja``; no offset
    adjustment is needed.
    """
    shape = (grid.nlay, grid.nrow, grid.ncol)
    ncells_per_layer = grid.nrow * grid.ncol
    right = np.full(grid.nnodes, -1, np.int64)
    front = np.full(grid.nnodes, -1, np.int64)
    lower = np.full(grid.nnodes, -1, np.int64)

    for i in range(grid.nnodes):
        for nzi in range(grid.ia[i], grid.ia[i + 1]):
            # ia/ja are 0-based: nzi is both the position in ja AND the
            # position in the flat flow-ja-face budget array.
            j = grid.ja[nzi]  # 0-based connected-cell index
            d = j - i
            if d <= 0:  # self, left, back, or upper
                continue
            elif d == 1 and grid.ncol > 1:  # right neighbor
                right[i] = nzi
            elif d == grid.ncol and ncells_per_layer > 1:  # front neighbor
                front[i] = nzi
            elif d == ncells_per_layer:  # lower neighbor
                lower[i] = nzi
            else:  # skips one or more layers: pass-through
                npassed = int(d / ncells_per_layer)
                for ipass in range(0, npassed):
                    lower[i + ipass * ncells_per_layer] = nzi

    return right.reshape(shape), front.reshape(shape), lower.reshape(shape)


def open_face_budgets_as_flowja(
    cbc_path: Path,
    header_list: list[Imeth1Header],
    grid_or_info,
) -> tuple[xr.DataArray, xr.DataArray]:
    """Return flow-ja-face as-is with connectivity. Works for both DIS and DISV."""
    flowja = cbc_open_imeth1_budgets(cbc_path, header_list)
    flowja = flowja.rename({"linear_index": "connection"})

    if isinstance(grid_or_info, dict):
        # DISV grb_info dict
        ia = grid_or_info["ia"]
        ja = grid_or_info["ja"]
    else:
        # DIS StructuredGrid with ia/ja properties
        ia = grid_or_info.ia
        ja = grid_or_info.ja

    # ia and ja are 0-based in both DIS and DISV (MfGrdFile converts on read).
    n = expand_indptr(ia)
    m = ja  # 0-based connected-cell indices
    nm = xr.DataArray(
        np.column_stack([n, m]),
        coords={"cell": ["n", "m"]},
        dims=["connection", "cell"],
    )
    return flowja, nm


def expand_indptr(ia) -> np.ndarray:
    n = np.diff(ia)
    return np.repeat(np.arange(ia.size - 1), n)


# DISV-specific budget functions


def disv_open_imeth1_budgets(
    cbc_path: Path,
    grb_info: dict[str, Any],
    header_list: list[Imeth1Header],
) -> xu.UgridDataArray:
    """
    Open the data for an imeth==1 budget section (DISV).

    Returns
    -------
    xu.UgridDataArray with dims ("time", "layer", face_dimension)
    """
    grid = grb_info["grid"]
    facedim = grb_info["face_dimension"]
    nlayer = grb_info["nlayer"]
    ncells_per_layer = grb_info["ncells_per_layer"]
    budgets = cbc_open_imeth1_budgets(cbc_path, header_list)
    coords = grb_info["coords"].copy() | {"time": budgets["time"]}

    da = xr.DataArray(
        data=budgets.data.reshape((budgets["time"].size, nlayer, ncells_per_layer)),
        coords=coords,
        dims=("time", "layer", facedim),
        name=budgets.name,
    )
    return xu.UgridDataArray(da, grid)


def disv_open_imeth6_budgets(
    cbc_path: Path,
    grb_info: dict[str, Any],
    header_list: list[Imeth6Header],
    return_variable: str = "budget",
    indices: np.ndarray | None = None,
) -> xu.UgridDataArray:
    """
    Open the data for an imeth==6 budget section (DISV).

    Returns
    -------
    xu.UgridDataArray with dims ("time", "layer", face_dimension)
    """
    dtype = np.dtype(
        [("id1", np.int32), ("id2", np.int32), ("budget", np.float64)]
        + [(name, np.float64) for name in header_list[0].auxtxt]
    )
    shape = (grb_info["nlayer"], grb_info["ncells_per_layer"])
    size = np.prod(shape)
    dask_list = []
    time = np.empty(len(header_list), dtype=np.float64)
    for i, header in enumerate(header_list):
        time[i] = header.totim
        a = dask.delayed(read_imeth6_budgets_dense)(
            cbc_path,
            header.nlist,
            dtype,
            header.pos,
            size,
            shape,
            return_variable,
            indices,
        )
        x = dask.array.from_delayed(a, shape=shape, dtype=np.float64)
        dask_list.append(x)

    daskarr = dask.array.stack(dask_list, axis=0)
    coords = grb_info["coords"].copy()
    coords["time"] = time
    name = header_list[0].text
    grid = grb_info["grid"]
    da = xr.DataArray(daskarr, coords, ("time", "layer", grb_info["face_dimension"]), name=name)
    return xu.UgridDataArray(da, grid)


# DISV face-budget helpers


def compute_flow_orientation(
    edge_face_connectivity: np.ndarray, face_coordinates: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Compute unit flow direction components (u, v) for each edge."""
    nedge = len(edge_face_connectivity)
    is_connection = edge_face_connectivity[:, 1] != XUGRID_FILL_VALUE
    edge_faces = edge_face_connectivity[is_connection]
    edge_faces.sort(axis=1)
    u = np.full(nedge, np.nan)
    v = np.full(nedge, np.nan)
    xy = face_coordinates[edge_faces]
    dx = xy[:, 1, 0] - xy[:, 0, 0]
    dy = xy[:, 1, 1] - xy[:, 0, 1]
    t = np.sqrt(dx**2 + dy**2)
    u[is_connection] = dx / t
    v[is_connection] = dy / t
    return u, v


def mf6_csr_to_coo(ia: np.ndarray, ja: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert 0-based CSR arrays (ia, ja) into COO row/col arrays.

    Both ``ia`` and ``ja`` are 0-based (as returned by
    :class:`~flopy.mf6.utils.binarygrid_util.MfGrdFile`).
    The returned ``i`` and ``j`` are also 0-based cell indices.
    """
    n = np.diff(ia)
    i = np.repeat(np.arange(ia.size - 1), n)
    j = ja  # already 0-based
    return i, j


def alt_cumsum(a):
    """Alternative cumsum, start 0 and omit the last value."""
    out = np.empty(a.size, a.dtype)
    out[0] = 0
    np.cumsum(a[:-1], out=out[1:])
    return out


def ragged_arange(n: np.ndarray) -> np.ndarray:
    """Equal to: np.concatenate([np.arange(e) for e in n])"""
    return alt_cumsum(np.ones(int(n.sum()), dtype=int)) - np.repeat(alt_cumsum(n), n)


def disv_indices(
    ia: np.ndarray,
    ja: np.ndarray,
    idomain: np.ndarray,
    edge_face_connectivity: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Infer lower and horizontal flow indices for DISV grids.

    Returns
    -------
    lower: ndarray of shape (nlayer, ncells_per_layer)
    horizontal: ndarray of shape (nlayer, nedge)
    """
    nlayer, ncells_per_layer = idomain.shape
    nedge = len(edge_face_connectivity)
    horizontal = np.full((nlayer, nedge), -1)
    lower = np.full((nlayer, ncells_per_layer), -1)

    i, j = mf6_csr_to_coo(ia, ja)
    diff = j - i
    is_vertical = diff >= ncells_per_layer
    is_horizontal = (diff > 0) & (~is_vertical)
    index = np.arange(j.size)

    # Vertical flows
    n_pass = diff[is_vertical] // ncells_per_layer
    ii = np.repeat(i[is_vertical], n_pass) + ragged_arange(n_pass) * ncells_per_layer
    lower.ravel()[ii] = np.repeat(index[is_vertical], n_pass)

    # Horizontal flows
    layered_edge_faces = np.add.outer(
        np.arange(nlayer) * ncells_per_layer,
        edge_face_connectivity,
    )
    is_active = idomain.ravel()[layered_edge_faces] == IDOMAIN_ACTIVE
    is_inner_edge = edge_face_connectivity[:, 1] != XUGRID_FILL_VALUE
    is_connection = (is_active.all(axis=2) & is_inner_edge[np.newaxis, :]).ravel()

    i_to_j = layered_edge_faces.reshape((-1, 2))[is_connection]
    order = np.argsort(np.lexsort(i_to_j.T[::-1]))

    horizontal.ravel()[is_connection] = index[is_horizontal][order]
    return lower, horizontal


def disv_to_horizontal_lower_indices(
    grb_info: dict[str, Any],
) -> tuple[xr.DataArray, xr.DataArray, xr.DataArray, xr.DataArray]:
    grid = grb_info["grid"]
    lower, horizontal = disv_indices(
        ia=grb_info["ia"],
        ja=grb_info["ja"],
        idomain=grb_info["idomain"],
        edge_face_connectivity=grid.edge_face_connectivity,
    )
    u, v = compute_flow_orientation(grid.edge_face_connectivity, grid.face_coordinates)
    return (
        xr.DataArray(horizontal, grb_info["coords"], dims=["layer", grid.edge_dimension]),
        xr.DataArray(u, dims=[grid.edge_dimension]),
        xr.DataArray(v, dims=[grid.edge_dimension]),
        xr.DataArray(lower, grb_info["coords"], dims=["layer", grid.face_dimension]),
    )


def disv_extract_lower_budget(budgets: xr.DataArray, index: xr.DataArray) -> xr.DataArray:
    face_dimension = index.dims[-1]
    coords = dict(index.coords)
    coords["time"] = budgets["time"]
    data = budgets.isel(linear_index=index.values.ravel()).data
    da = xr.DataArray(
        data=data.reshape((budgets["time"].size, *index.shape)),
        coords=coords,
        dims=("time", "layer", face_dimension),
        name="flow-ja-face",
    )
    return da.where(index >= 0, other=0.0)


def disv_extract_horizontal_budget(budgets: xr.DataArray, index: xr.DataArray) -> xr.DataArray:
    """
    Horizontal flows from the flow-ja-face array.
    """
    edge_dimension = index.dims[-1]
    coords = dict(index.coords)
    coords["time"] = budgets["time"]
    data = budgets.isel(linear_index=index.values.ravel()).data
    da = xr.DataArray(
        data=data.reshape((budgets["time"].size, *index.shape)),
        coords=coords,
        dims=("time", "layer", edge_dimension),
        name="flow-ja-face",
    )
    return da.where(index >= 0, other=0.0)


def disv_open_face_budgets(
    cbc_path: Path,
    grb_info: dict[str, Any],
    header_list: list[Imeth1Header],
) -> tuple[xu.UgridDataArray, xu.UgridDataArray, xu.UgridDataArray, xu.UgridDataArray]:
    """
    Open the flow-ja-face and extract horizontal + lower face flows for DISV.

    Returns
    -------
    horizontal, flow_x, flow_y, lower: xu.UgridDataArray
    """
    horizontal_index, u, v, lower_index = disv_to_horizontal_lower_indices(grb_info)
    budgets = cbc_open_imeth1_budgets(cbc_path, header_list)
    horizontal = disv_extract_horizontal_budget(budgets, horizontal_index)
    lower = disv_extract_lower_budget(budgets, lower_index)
    flow_x = -horizontal * u
    flow_y = -horizontal * v
    grid = grb_info["grid"]
    return (
        xu.UgridDataArray(horizontal, grid),
        xu.UgridDataArray(flow_x, grid),
        xu.UgridDataArray(flow_y, grid),
        xu.UgridDataArray(lower, grid),
    )
