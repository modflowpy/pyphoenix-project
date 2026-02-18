import os
import struct
from pathlib import Path

import dask
import numpy as np
import pandas as pd
import xarray as xr
import xugrid as xu
from flopy.discretization import StructuredGrid

from flopy4.adapters import read_binary_grid_file

from .grid import get_coords


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
    hds_path: pathlib.Path
    grb_path: pathlib.Path
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


def assign_datetime_coords(
    da: xr.DataArray,
    simulation_start_time: np.datetime64,
    time_unit: str | None = "d",
) -> xr.DataArray:
    if "time" not in da.coords:
        raise ValueError("cannot convert time column, because a time column could not be found")

    time = pd.Timestamp(simulation_start_time) + pd.to_timedelta(da["time"], unit=time_unit)
    return da.assign_coords(time=time)


def _to_nan(a: np.ndarray, dry_nan: bool) -> np.ndarray:
    # TODO: this could really use a docstring?
    a[a == 1e30] = np.nan
    if dry_nan:
        a[a == -1e30] = np.nan
    return a
