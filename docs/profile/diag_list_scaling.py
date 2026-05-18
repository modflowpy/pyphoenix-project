"""
Diagnostic: flopy4 list Rch write-time scaling.

Builds a minimal 1-layer structured grid at increasing cell counts and times
the write for each size.  The shape of the curve (O(n), O(n²), …) points to
where the bottleneck lives.

Sizes tested: 1K, 5K, 25K, 100K, 250K cells (single stress period, 1 run each).
If a run exceeds 60 s it is skipped so the script stays interactive.

Optional: pass --profile to run cProfile on the 25K-cell case and print the
top 20 cumulative-time frames.
"""

import argparse
import cProfile
import io
import pstats
import tempfile
import time
from pathlib import Path

import numpy as np

import flopy4

SKIP_THRESHOLD = 60.0  # seconds


def build_and_time(n: int, ws: Path) -> float | None:
    """Build a minimal flopy4 Rch(list) simulation with n cells and time write()."""
    ncol = n
    nrow = 1
    nlay = 1
    nper = 1

    grid = flopy4.mf6.utils.grid.StructuredGrid(
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        top=np.zeros((nrow, ncol)),
        botm=np.full((nlay, nrow, ncol), -10.0),
        delr=np.full(ncol, 10.0),
        delc=np.full(nrow, 10.0),
        idomain=np.ones((nlay, nrow, ncol), dtype=int),
    )
    dims = {"nper": nper, "ncpl": nrow * ncol, **dict(grid.dataset.sizes)}

    rch_dict = {0: {(0, 0, c): 0.001 for c in range(ncol)}}

    dis = flopy4.mf6.gwf.Dis.from_grid(grid=grid)
    ic = flopy4.mf6.gwf.Ic(strt=0.0, dims=dims)
    npf = flopy4.mf6.gwf.Npf(
        icelltype=np.zeros((nlay, nrow, ncol), dtype=int),
        k=np.ones((nlay, nrow, ncol)),
        dims=dims,
    )
    rch = flopy4.mf6.gwf.Rch(recharge=rch_dict, dims=dims)
    gwf = flopy4.mf6.gwf.Gwf(dis=grid, ic=ic, npf=npf, rch=[rch], dims=dims)
    ims = flopy4.mf6.Ims(
        outer_dvclose=1e-6,
        outer_maximum=50,
        inner_dvclose=1e-6,
        rclose=flopy4.mf6.Ims.Rclose(inner_rclose=0.01),
        inner_maximum=50,
        linear_acceleration="cg",
        models=["diag"],
    )
    time4 = flopy4.mf6.utils.time.Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    ws.mkdir(parents=True, exist_ok=True)
    sim = flopy4.mf6.simulation.Simulation(
        name="diag",
        tdis=flopy4.mf6.simulation.Tdis.from_time(time4),
        models={"diag": gwf},
        solutions={"ims": ims},
        workspace=ws,
    )

    t0 = time.perf_counter()
    sim.write()
    return time.perf_counter() - t0


def profile_write(n: int, ws: Path) -> None:
    """Run cProfile on write() for n cells and print top-20 frames."""
    # Build once outside profiler so construction cost is excluded
    ncol = n
    nrow = 1
    nlay = 1
    nper = 1

    grid = flopy4.mf6.utils.grid.StructuredGrid(
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        top=np.zeros((nrow, ncol)),
        botm=np.full((nlay, nrow, ncol), -10.0),
        delr=np.full(ncol, 10.0),
        delc=np.full(nrow, 10.0),
        idomain=np.ones((nlay, nrow, ncol), dtype=int),
    )
    dims = {"nper": nper, "ncpl": nrow * ncol, **dict(grid.dataset.sizes)}
    rch_dict = {0: {(0, 0, c): 0.001 for c in range(ncol)}}

    dis = flopy4.mf6.gwf.Dis.from_grid(grid=grid)
    ic = flopy4.mf6.gwf.Ic(strt=0.0, dims=dims)
    npf = flopy4.mf6.gwf.Npf(
        icelltype=np.zeros((nlay, nrow, ncol), dtype=int),
        k=np.ones((nlay, nrow, ncol)),
        dims=dims,
    )
    rch = flopy4.mf6.gwf.Rch(recharge=rch_dict, dims=dims)
    gwf = flopy4.mf6.gwf.Gwf(dis=grid, ic=ic, npf=npf, rch=[rch], dims=dims)
    ims = flopy4.mf6.Ims(
        outer_dvclose=1e-6,
        outer_maximum=50,
        inner_dvclose=1e-6,
        rclose=flopy4.mf6.Ims.Rclose(inner_rclose=0.01),
        inner_maximum=50,
        linear_acceleration="cg",
        models=["diag"],
    )
    time4 = flopy4.mf6.utils.time.Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    ws.mkdir(parents=True, exist_ok=True)
    sim = flopy4.mf6.simulation.Simulation(
        name="diag",
        tdis=flopy4.mf6.simulation.Tdis.from_time(time4),
        models={"diag": gwf},
        solutions={"ims": ims},
        workspace=ws,
    )

    pr = cProfile.Profile()
    pr.enable()
    sim.write()
    pr.disable()

    buf = io.StringIO()
    ps = pstats.Stats(pr, stream=buf).sort_stats("cumulative")
    ps.print_stats(20)
    print(buf.getvalue())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--profile",
        action="store_true",
        help="run cProfile on the 25K-cell case after scaling test",
    )
    p.add_argument(
        "--profile-n", type=int, default=25_000, help="cell count to profile (default: 25000)"
    )
    args = p.parse_args()

    sizes = [1_000, 5_000, 25_000, 100_000, 250_000]
    print(f"{'cells':>10}  {'time (s)':>10}  {'ratio':>8}  {'~complexity':>12}")
    print("-" * 48)

    prev_t = None
    prev_n = None
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for n in sizes:
            ws = tmp / f"n{n}"
            t0 = time.perf_counter()
            elapsed = build_and_time(n, ws)
            if elapsed is None:
                print(f"{n:>10}  {'SKIPPED':>10}")
                break

            if elapsed > SKIP_THRESHOLD:
                print(f"{n:>10}  {elapsed:>10.3f}  [exceeded {SKIP_THRESHOLD:.0f}s — stopping]")
                break

            if prev_t is not None and prev_t > 0:
                ratio = elapsed / prev_t
                n_ratio = n / prev_n
                complexity = ratio / n_ratio  # ~1 for O(n), ~n_ratio for O(n²)
                complexity_str = (
                    f"~O(n^{1 + (complexity - 1) / (n_ratio - 1):.2f})" if n_ratio > 1 else "—"
                )
                print(f"{n:>10}  {elapsed:>10.3f}  {ratio:>8.2f}x  {complexity_str:>12}")
            else:
                print(f"{n:>10}  {elapsed:>10.3f}  {'—':>8}  {'—':>12}")

            prev_t = elapsed
            prev_n = n

        if args.profile:
            pws = tmp / f"profile_n{args.profile_n}"
            print(f"\n--- cProfile: {args.profile_n:,} cells ---")
            profile_write(args.profile_n, pws)


if __name__ == "__main__":
    main()
