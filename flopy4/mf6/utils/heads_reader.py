import os
import struct
from pathlib import Path

import dask
import numpy as np
import xarray as xr
import xugrid as xu
from flopy.discretization import StructuredGrid

from flopy4.adapters import read_binary_grid_file

from .grid import get_coords
from .time import assign_datetime_coords


def open_hds(
    hds_path: Path,
    grb_path: Path,
    dry_nan: bool = False,
    simulation_start_time: np.datetime64 | None = None,
    time_unit: str | None = "d",
) -> xr.DataArray | xu.UgridDataArray:
    """
    Open modflow6 heads (.hds) file.

    The data is lazily read per timestep and automatically converted into
    (dense) xr.DataArrays for DIS or xu.UgridDataArrays for DISV.
    The conversion is done via the information stored in the Binary Grid file
    (GRB).


    Parameters
    ----------
    hds_path: pathlib.Path, binary head or netcdf file path
    grb_path: pathlib.Path, binary grid file
    dry_nan: bool, default value: False.
        Whether to convert dry values to NaN.
    simulation_start_time : Optional datetime
        The time and date corresponding to the beginning of the simulation.
        Use this to convert the time coordinates of the output array to
        calendar time/dates.
        Time_unit must also be present if this argument is present.
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
        Units "month" or "year" are not supported,
        as they do not represent unambiguous timedelta values durations.

    Returns
    -------
    head: xr.DataArray or xu.UgridDataArray
    """
    grb_info = read_binary_grid_file(grb_path)

    if hds_path.suffix == ".nc":
        return _open_hds_netcdf(hds_path, grb_info, dry_nan)

    if grb_info["grid_type"] == "DIS":
        return _open_hds_dis(hds_path, grb_info["grid"], dry_nan, simulation_start_time, time_unit)
    elif grb_info["grid_type"] == "DISV":
        return _open_hds_disv(hds_path, grb_info, dry_nan, simulation_start_time, time_unit)
    else:
        raise ValueError(f"Unsupported grid type: {grb_info['grid_type']}")


def _open_hds_dis(
    path: Path,
    grid: StructuredGrid,
    dry_nan: bool,
    simulation_start_time: np.datetime64 | None = None,
    time_unit: str | None = "d",
) -> xr.DataArray:
    nlayer, nrow, ncol = (
        grid.nlay,
        grid.nrow,
        grid.ncol,
    )
    ncells_per_layer = nrow * ncol
    filesize = os.path.getsize(path)
    ntime = filesize // (nlayer * (52 + (ncells_per_layer * 8)))
    coords = get_coords(grid)
    coords["time"] = read_times(path, ntime, nlayer, ncells_per_layer)

    dask_list = []
    for i in range(ntime):
        pos = i * (nlayer * (52 + ncells_per_layer * 8))
        a = dask.delayed(read_hds_timestep)(path, nlayer, ncells_per_layer, dry_nan, pos)
        x = dask.array.from_delayed(a, shape=(nlayer, ncells_per_layer), dtype=np.float64)
        dask_list.append(x)

    daskarr = dask.array.stack(dask_list, axis=0)
    # reshape to (ntime, nlayer, nrow, ncol)
    daskarr = daskarr.reshape((ntime, nlayer, nrow, ncol))
    data_array = xr.DataArray(daskarr, coords, ("time", "layer", "y", "x"), name="head")
    if simulation_start_time is not None:
        data_array = assign_datetime_coords(data_array, simulation_start_time, time_unit)
    return data_array


def _open_hds_disv(
    path: Path,
    grb_info: dict,
    dry_nan: bool,
    simulation_start_time: np.datetime64 | None = None,
    time_unit: str | None = "d",
) -> xu.UgridDataArray:
    grid = grb_info["grid"]
    nlayer = grb_info["nlayer"]
    ncells_per_layer = grb_info["ncells_per_layer"]
    facedim = grb_info["face_dimension"]

    filesize = os.path.getsize(path)
    ntime = filesize // (nlayer * (52 + (ncells_per_layer * 8)))
    times = read_times(path, ntime, nlayer, ncells_per_layer)

    coords = grb_info["coords"].copy()
    coords["time"] = times

    dask_list = []
    for i in range(ntime):
        pos = i * (nlayer * (52 + ncells_per_layer * 8))
        a = dask.delayed(read_hds_timestep)(path, nlayer, ncells_per_layer, dry_nan, pos)
        x = dask.array.from_delayed(a, shape=(nlayer, ncells_per_layer), dtype=np.float64)
        dask_list.append(x)

    daskarr = dask.array.stack(dask_list, axis=0)
    da = xr.DataArray(daskarr, coords, ("time", "layer", facedim), name="head")

    if simulation_start_time is not None:
        da = assign_datetime_coords(da, simulation_start_time, time_unit)
    return xu.UgridDataArray(da, grid)


def _open_hds_netcdf(
    path: Path,
    grb_info: dict,
    dry_nan: bool,
) -> xr.DataArray | xu.UgridDataArray:
    """
    Open a MODFLOW 6 heads NetCDF file.

    Two NetCDF formats are supported:

    1. **CF-UGRID layered** (``mesh`` global attribute present): one variable
       per layer (``head_l1``, ``head_l2``, …) on ``(time, nmesh_face)``.
       Written by MODFLOW 6 for both DIS and DISV grids.

    2. **Conventional CF structured** (no ``mesh`` global attribute): a single
       ``head`` variable on ``(time, z, y, x)`` with x/y as dimension
       coordinates.  Written by MODFLOW 6 for DIS grids only.

    The GRB file grid is used as the authoritative grid topology for the
    returned array, ensuring consistency with binary-format readers.

    Parameters
    ----------
    path : Path
        Path to the NetCDF heads file.
    grb_info : dict
        Grid info dict returned by ``read_binary_grid_file``.
    dry_nan : bool
        Whether to convert dry cell values (-1e30) to NaN.

    Returns
    -------
    xr.DataArray
        For DIS grids: dims ``(time, layer, y, x)``.
    xu.UgridDataArray
        For DISV grids: dims ``(time, layer, <face_dim>)``.
    """
    # Open with chunks={"time": 1} so each timestep is a separate dask chunk,
    # matching the per-timestep lazy loading of the binary reader.
    ds = xr.open_dataset(path, chunks={"time": 1})
    grid_type = ds.attrs.get("modflow_grid", "").upper()

    # Validate that the NetCDF grid type is consistent with the GRB file.
    _NC_TO_GRB = {"STRUCTURED": "DIS", "VERTEX": "DISV"}
    grb_grid_type = grb_info["grid_type"]
    if grid_type and _NC_TO_GRB.get(grid_type) != grb_grid_type:
        raise ValueError(
            f"Grid type mismatch: GRB reports {grb_grid_type!r} but NetCDF "
            f"'modflow_grid' attribute is {grid_type!r}"
        )

    # Time is already CF-encoded datetime64; load eagerly (small coordinate).
    time_values = ds["time"].values

    # --- Conventional CF structured: no "mesh" global attribute ---
    # Single head(time, z, y, x) variable; x/y are dimension coordinates.
    if "mesh" not in ds.attrs:
        if grid_type != "STRUCTURED":
            raise ValueError(
                f"Conventional CF format (no 'mesh' attribute) is only supported "
                f"for STRUCTURED grids, got {grid_type!r} in {path.name}."
            )
        grid = grb_info["grid"]
        data = ds["head"].data  # (ntime, nlayer, nrow, ncol) dask array
        data = _dask_to_nan(data, dry_nan)
        coords = get_coords(grid)
        coords["time"] = time_values
        return xr.DataArray(data, coords, ("time", "layer", "y", "x"), name="head")

    # --- CF-UGRID layered: head_l1, head_l2, ... on (time, nmesh_face) ---
    head_vars = sorted(
        [v for v in ds.data_vars if v.startswith("head_l")],  # type: ignore
        key=lambda v: int(v[len("head_l") :]),  # type: ignore
    )
    if not head_vars:
        raise ValueError(f"No head layer variables (head_l1, head_l2, ...) found in {path.name}")

    nlayer = len(head_vars)

    if grid_type == "VERTEX":
        # DISV: stack per-layer dask arrays -> (ntime, nlayer, ncpl)
        # Use grb grid and face_dimension for consistency with binary reader.
        grid = grb_info["grid"]
        facedim = grb_info["face_dimension"]

        arrays = [ds[v].data for v in head_vars]  # each (ntime, ncpl) dask array
        data = dask.array.stack(arrays, axis=1)  # (ntime, nlayer, ncpl)
        data = _dask_to_nan(data, dry_nan)

        coords = {"time": time_values, "layer": np.arange(1, nlayer + 1)}
        da = xr.DataArray(data, coords, ("time", "layer", facedim), name="head")
        return xu.UgridDataArray(da, grid)

    elif grid_type == "STRUCTURED":
        # DIS: stack per-layer dask arrays and reshape nmesh_face -> (nrow, ncol)
        grid = grb_info["grid"]
        nrow, ncol = grid.nrow, grid.ncol
        ntime = ds.sizes["time"]

        arrays = [ds[v].data for v in head_vars]  # each (ntime, nmesh_face) dask array
        data = dask.array.stack(arrays, axis=1)  # (ntime, nlayer, nmesh_face)
        data = data.reshape(ntime, nlayer, nrow, ncol)
        data = _dask_to_nan(data, dry_nan)

        coords = get_coords(grid)
        coords["time"] = time_values
        return xr.DataArray(data, coords, ("time", "layer", "y", "x"), name="head")

    else:
        raise ValueError(
            f"Unsupported modflow_grid type {grid_type!r} in {path.name}. "
            "Expected 'VERTEX' or 'STRUCTURED'."
        )


def read_times(path: Path, ntime: int, nlayer: int, ncells_per_layer: int) -> np.ndarray:
    """
    Reads all total simulation times.
    """
    times = np.empty(ntime, dtype=np.float64)

    # Compute how much to skip to the next timestamp
    start_of_header = 16
    rest_of_header = 28
    data_single_layer = ncells_per_layer * 8
    header = 52
    nskip = (
        rest_of_header
        + data_single_layer
        + (nlayer - 1) * (header + data_single_layer)
        + start_of_header
    )

    with open(path, "rb") as f:
        f.seek(start_of_header)
        for i in range(ntime):
            times[i] = struct.unpack("d", f.read(8))[0]  # total simulation time
            f.seek(nskip, 1)
    return times


def read_hds_timestep(
    path: Path, nlayer: int, ncells_per_layer: int, dry_nan: bool, pos: int
) -> np.ndarray:
    """
    Reads all values of one timestep. Returns shape (nlayer, ncells_per_layer).
    """
    with open(path, "rb") as f:
        f.seek(pos)
        a1d = np.empty(nlayer * ncells_per_layer, dtype=np.float64)
        for k in range(nlayer):
            f.seek(52, 1)  # skip kstp, kper, pertime
            a1d[k * ncells_per_layer : (k + 1) * ncells_per_layer] = np.fromfile(
                f, np.float64, ncells_per_layer
            )

    a2d = a1d.reshape((nlayer, ncells_per_layer))
    return _to_nan(a2d, dry_nan)


def _dask_to_nan(a: dask.array.Array, dry_nan: bool) -> dask.array.Array:
    a = dask.array.where(a == 1e30, np.nan, a)
    if dry_nan:
        a = dask.array.where(a == -1e30, np.nan, a)
    return a


def _to_nan(a: np.ndarray, dry_nan: bool) -> np.ndarray:
    """
    Replace MODFLOW 6 no-data sentinels (1e30) with NaN, in-place.

    If *dry_nan* is True, also replace dry-cell values (-1e30) with NaN.
    """
    a[a == 1e30] = np.nan
    if dry_nan:
        a[a == -1e30] = np.nan
    return a
