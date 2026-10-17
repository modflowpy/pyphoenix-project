"""Frenchman Flat writes (see `_ff.py`): flopy4's input forms, and flopy3.

Each variant builds the model, untimed, then writes it, into the same
directory each round:

- `list` -- WEL lists.
- `grid` -- WELG grids (3 x 7.5M elements), as text.
- `netcdf-list` -- WEL lists; arrays in a layered-mesh NetCDF file.
- `netcdf-mesh` -- WELG, in a layered-mesh NetCDF file, with a 2D mesh file.
- `netcdf-structured` -- WELG, in a CF structured NetCDF file.
- `flopy3` -- flopy3, WEL lists.
"""

import pytest
from _ff import build_flopy3, build_flopy4
from _scenario import bench, netcdf_write

NETCDF = {
    "netcdf-list": dict(layered_mesh=True, mesh2d=False),
    "netcdf-mesh": dict(layered_mesh=True, mesh2d=True),
    "netcdf-structured": dict(layered_mesh=False, mesh2d=False),
}


@pytest.mark.parametrize("variant", ["list", "grid", *NETCDF, "flopy3"])
def test_ff_write(benchmark, quiet, tmp_path, variant):
    benchmark.group = "ff-write"
    if variant == "flopy3":
        sim3 = build_flopy3(tmp_path)
        bench(benchmark, lambda: sim3.write_simulation(silent=True))
        return
    m = build_flopy4(tmp_path, wel="list" if variant in ("list", "netcdf-list") else "grid")
    if variant in NETCDF:
        bench(benchmark, netcdf_write(m.sim, m.gwf, m.grid, m.time, **NETCDF[variant]))
    else:
        bench(benchmark, m.sim.write)
