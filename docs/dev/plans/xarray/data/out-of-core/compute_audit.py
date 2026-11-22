"""Which flopy4 operations compute a lazy array, where, and how much do they hold?

Blocks are generated on demand from each cell's index, so values don't depend on
chunking and a numpy control can be byte-compared. Each block computed is
counted and attributed to the innermost flopy4 frame on the stack (the scheduler
is synchronous). Everything is warmed up first, so peaks exclude template
compilation and first-use imports.
"""

import collections
import gc
import shutil
import sys
import tempfile
import traceback
import tracemalloc
import warnings
from pathlib import Path

import dask
import dask.array as da
import numpy as np

import flopy4
from flopy4.mf6.gwf import Gwf, Ic, Npf, Rcha, Welg
from flopy4.mf6.ims import Ims
from flopy4.mf6.netcdf import NetCDFModel
from flopy4.mf6.simulation import Simulation, Tdis
from flopy4.mf6.utils.grid import StructuredGrid
from flopy4.mf6.utils.time import Time
from flopy4.mf6.write_context import WriteContext

dask.config.set(scheduler="synchronous")
warnings.simplefilter("ignore")

computed = 0
sites: collections.Counter = collections.Counter()


def _values(shape, location):
    grids = np.ogrid[tuple(slice(a, b) for a, b in location)]
    idx = sum(g * (7**i + 1000 * i) for i, g in enumerate(grids))
    return 1.0 + (idx * 2654435761 % 1000003) / 1000003.0


def _gen(block, block_info=None):
    global computed
    if block.size == 0 or block_info is None:
        return block
    computed += 1
    site = "?"
    for fr in reversed(traceback.extract_stack()):
        if "/flopy4/" in fr.filename:
            site = f"{Path(fr.filename).name}:{fr.name}"
            break
    sites[site] += 1
    return _values(block.shape, block_info[0]["array-location"])


def lazy(shape, chunks):
    return da.zeros(shape, chunks=chunks).map_blocks(_gen, dtype=float)


def eager(shape):
    return _values(shape, [(0, n) for n in shape])


def measure(label, fn, total, mb):
    global computed
    computed = 0
    sites.clear()
    gc.collect()
    tracemalloc.start()
    err, out = "", None
    try:
        out = fn()
    except Exception as e:  # noqa: BLE001
        err = f"  !! {type(e).__name__}: {str(e)[:80]}"
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    where = ", ".join(f"{k}×{v}" for k, v in sites.most_common(3))
    print(
        f"  {label:<30} blocks {computed:>4}/{total:<4} "
        f"peak {peak / 1e6:7.1f} MB ({peak / 1e6 / mb:5.2f}× array){err}  {where}",
        flush=True,
    )
    return out


def build(ws, nlay, nrow, ncol, nper, **pkgs):
    grid = StructuredGrid(
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        delr=np.ones(ncol),
        delc=np.ones(nrow),
        top=np.ones((nrow, ncol)),
        botm=np.stack([np.full((nrow, ncol), -float(i + 1)) for i in range(nlay)]),
    )
    time = Time(perlen=[1.0] * nper, nstp=[1] * nper, tsmult=[1.0] * nper)
    dims = {"nper": nper, **grid.dims}
    npf_k = pkgs.pop("k", 1.0)
    gwf = Gwf(name="m", dis=grid, dims=dims)
    Ic(parent=gwf, dims=dims, strt=1.0)
    npf = Npf(parent=gwf, dims=dims, icelltype=np.zeros(nlay * nrow * ncol, dtype=int), k=npf_k)
    extra = {}
    for name, (cls, kw) in pkgs.items():
        extra[name] = cls(parent=gwf, dims=dims, **kw)
    sim = Simulation(
        name="s",
        tdis=Tdis.from_time(time),
        models=[gwf],
        solutiongroup=[Ims(linear_acceleration="cg")],
        workspace=ws,
    )
    return sim, gwf, npf, grid, time, extra


def netcdf(gwf, grid, time, ws):
    NetCDFModel.from_model(gwf, grid=grid, time=time).to_netcdf(Path(ws) / "m.input.nc")


def griddata_ops(name, ws, make_k, shape3, total, mb):
    print(f"\n{name}")
    ws = Path(ws)
    ws.mkdir()
    built = measure("construct", lambda: build(ws, *shape3, 1, k=make_k()), total, mb)
    if built is None:
        return None
    sim, gwf, npf, grid, time, _ = built
    measure("npf.to_xarray()", npf.to_xarray, total, mb)
    measure("write inline text", sim.write, total, mb)
    inline = (ws / "m.npf").read_bytes() if (ws / "m.npf").exists() else None
    if inline is None:
        cands = list(ws.rglob("*.npf"))
        inline = cands[0].read_bytes() if cands else b""
    measure(
        "write open/close",
        lambda: sim.write(context=WriteContext(array_format="open/close")),
        total,
        mb,
    )
    measure(
        "write binary", lambda: sim.write(context=WriteContext(array_format="binary")), total, mb
    )
    measure("netcdf from_model+to_netcdf", lambda: netcdf(gwf, grid, time, ws), total, mb)
    return inline


root = Path(tempfile.mkdtemp(dir=sys.argv[1]))

# warm up on a tiny model: templates, lazy imports, netcdf backend
s = (2, 3, 4)
print("warming up", flush=True)
for mk in (lambda: lazy((2, 3, 4), (1, 3, 4)), lambda: eager((2, 3, 4))):
    w = root / f"warm{np.random.randint(1e9)}"
    w.mkdir()
    sim, gwf, npf, grid, time, _ = build(
        w,
        *s,
        2,
        k=mk(),
        rcha=(Rcha, {"recharge": {0: lazy((1, 3, 4), (1, 3, 4))}}),
    )
    npf.to_xarray()
    sim.write()
    sim.write(context=WriteContext(array_format="open/close"))
    sim.write(context=WriteContext(array_format="binary"))
    netcdf(gwf, grid, time, w)

NLAY, NROW, NCOL = 8, 300, 400
NODES = NLAY * NROW * NCOL
MB = NODES * 8 / 1e6
S3 = (NLAY, NROW, NCOL)
print(f"\ngrid {S3}; k = {MB:.0f} MB, one layer = {MB / NLAY:.0f} MB")

base = griddata_ops("numpy control", root / "np", lambda: eager(S3), S3, 0, MB)
for label, shape, chunks, d in [
    ("dask, chunk per layer", S3, (1, NROW, NCOL), "layer"),
    ("dask, tiled (4,100,100)", S3, (4, 100, 100), "tile"),
    ("dask, flat (nodes,) 100 chunks", (NODES,), (NODES // 100,), "flat"),
]:
    n = lazy(shape, chunks).npartitions
    if shape == S3:
        make = lambda shape=shape, chunks=chunks: lazy(shape, chunks)  # noqa: E731
    else:
        # flat values must match the 3-D control's, so reshape a 3-D source's order
        make = lambda: lazy(S3, (1, NROW, NCOL)).reshape(-1).rechunk(NODES // 100)  # noqa: E731
    out = griddata_ops(label, root / d, make, S3, n, MB)
    if out is not None and base is not None:
        print(f"  inline .npf bytes == numpy control: {out == base}")

# period arrays
NPER = 6
PL = (1, NROW, NCOL)
print(f"\nRCHA, {NPER} periods; one period = {NROW * NCOL * 8 / 1e6:.0f} MB")
ws = root / "rcha"
ws.mkdir()
total = 5 * NPER
b = measure(
    "construct, dict of lazy",
    lambda: build(
        ws,
        *S3,
        NPER,
        rcha=(Rcha, {"recharge": {p: lazy(PL, (1, NROW // 5, NCOL)) for p in range(NPER)}}),
    ),
    total,
    2.0,
)
if b:
    sim, gwf, _, grid, time, ex = b
    measure("to_xarray", ex["rcha"].to_xarray, total, 2.0)
    measure("write inline", sim.write, total, 2.0)
    measure("netcdf from_model+to_netcdf", lambda: netcdf(gwf, grid, time, ws), total, 2.0)

print(f"\nWELG, {NPER} periods; one period = {MB:.0f} MB")
ws = root / "welg"
ws.mkdir()
total = NLAY * NPER
b = measure(
    "construct, dict of lazy",
    lambda: build(
        ws,
        *S3,
        NPER,
        welg=(Welg, {"q": {p: lazy(S3, (1, NROW, NCOL)) for p in range(NPER)}}),
    ),
    total,
    MB,
)
if b:
    sim, gwf, _, grid, time, ex = b
    measure("to_xarray", ex["welg"].to_xarray, total, MB)
    measure("write inline", sim.write, total, MB)

print("\nRCHA dense (nper, ...) lazy")
ws = root / "dense"
ws.mkdir()
measure(
    "construct",
    lambda: build(
        ws, *S3, NPER, rcha=(Rcha, {"recharge": lazy((NPER, *PL), (1, 1, NROW, NCOL))})
    ),
    NPER,
    2.0,
)

shutil.rmtree(root, ignore_errors=True)
