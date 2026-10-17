"""Shared by the profiling scenarios."""

from pathlib import Path

ROUNDS = 3


def bench(benchmark, fn, slow: bool = False) -> None:
    """Time `fn`: `ROUNDS` rounds after a warm-up, or, if `slow`, once."""
    if slow:
        benchmark.pedantic(fn, rounds=1, iterations=1)
    else:
        benchmark.pedantic(fn, rounds=ROUNDS, iterations=1, warmup_rounds=1)


def spd(data: dict[int, dict]) -> dict[int, list]:
    """Per-period ``{cellid: value}`` as list stress period data."""
    return {period: list(cells.items()) for period, cells in data.items()}


def netcdf_write(sim, gwf, grid, time, *, layered_mesh: bool, mesh2d: bool):
    """A function writing `sim` with `gwf`'s array input in a NetCDF file:
    layered-mesh or CF structured, and with or without a 2D mesh file."""
    import flopy4
    from flopy4.mf6.enums import NetCDFFormat

    nc = Path(sim.workspace) / f"{gwf.name}.input.nc"
    gwf.netcdf_input_file = nc
    gwf.netcdf_mesh2d_file = Path(f"{gwf.name}.nc") if mesh2d else None
    fmt = {"netcdf_format": NetCDFFormat.LAYERED_MESH} if layered_mesh else {}
    model = flopy4.mf6.netcdf.NetCDFModel.from_model(gwf, grid=grid, time=time, **fmt)

    def write():
        model.to_netcdf(nc)
        with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
            sim.write()

    return write
