"""What the benchmarks time, per library: load, materialize and write.

Every benchmark, check and subprocess goes through these functions, so
the two libraries' setup (flopy3's load options above all) can't drift
between benchmarks.

Standard library only at module level: `_worker.py` imports this module in
a fresh interpreter to time the libraries' own imports, so heavy imports
stay inside the functions.

What each library reads, and when (flopy 3.11.0; see
docs/dev/load-benchmarks.md for the evidence):

- flopy3 ``MFSimulation.load(lazy_io=False, verify_data=False)``, with
  ``use_pandas=True`` (the default), parses internal data at load. It does
  *not* read ``OPEN/CLOSE`` array files: it stores the path and reads the
  file on every ``get_data()``, without caching. ``OPEN/CLOSE`` list files
  are read at load, but only because ``auto_set_sizes`` (on whenever
  ``lazy_io`` is off) calls ``get_data()`` to size ``maxbound``; they aren't
  cached either. It also loads packages flopy4 has no component for.
- flopy4 ``Simulation.load`` reads everything it reads eagerly, but skips
  packages and child files it has no component for.

So the fair comparison is ``load + materialize``, with flopy3 restricted
via ``load_only`` to the package types flopy4 loaded, on models where both
then open exactly the same set of files (`_check.py`).
"""

from __future__ import annotations

from pathlib import Path

# flopy3 load options, fixed for every benchmark
FLOPY3_OPTIONS = {"verbosity_level": 0, "lazy_io": False, "verify_data": False, "use_pandas": True}

LIBRARIES = ("flopy3", "flopy4")


def silence() -> None:
    """Silence warnings and logging; printing isn't what's measured."""
    import logging
    import warnings

    warnings.simplefilter("ignore")
    logging.disable(logging.CRITICAL)


def load_only_for(dfn_names) -> list[str]:
    """flopy3 `load_only` entries for the flopy4 components that loaded.

    Array-based rch/evt (``rcha``) and grid-based (``chdg``) packages are
    distinct flopy4 components but share one flopy3 ftype (``rch``, ``chd``).
    flopy3 always loads the discretization, the TDIS and namefiles."""
    out = set()
    for name in dfn_names:
        component, _, sub = name.partition("-")
        if component == "exg":
            out.add(f"{sub[:3]}6-{sub[3:]}6")
            continue
        out.add(sub)
        if sub in ("rcha", "evta") or (len(sub) == 4 and sub.endswith("g")):
            out.add(sub[:-1])
    return sorted(out)


def load_flopy3(ws: Path, load_only: list[str] | None = None):
    import flopy

    return flopy.mf6.MFSimulation.load(sim_ws=str(ws), load_only=load_only, **FLOPY3_OPTIONS)


def load_flopy4(ws: Path):
    from flopy4.mf6.simulation import Simulation

    return Simulation.load(Path(ws) / "mfsim.nam")


def package_files(sim, ws: Path) -> list[tuple[Path, str]]:
    """Every package file a loaded flopy4 simulation holds (nested ones like
    TS6/OBS6 included), with its DFN name."""
    from flopy4.mf6.package import Package

    def walk(component):
        for child in component._children.values():
            if isinstance(child, Package):
                yield Path(ws) / child.filename, child.dfn_name
            yield from walk(child)

    return list(walk(sim))


class Tally:
    """What materializing touched: how many values, their sum, and the sum
    of their magnitudes (the scale for comparing sums). NaNs are skipped."""

    __slots__ = ("count", "total", "magnitude")

    def __init__(self) -> None:
        self.count = 0
        self.total = 0.0
        self.magnitude = 0.0

    def add(self, values) -> None:
        import numpy as np

        if values.size:
            self.count += values.size
            total, magnitude = values.sum(), np.abs(values).sum()
            if total != total:  # NaN
                total, magnitude = np.nansum(values), np.nansum(np.abs(values))
            self.total += float(total)
            self.magnitude += float(magnitude)

    def add_scalar(self, value) -> None:
        self.count += 1
        if value == value:  # not NaN
            self.total += value
            self.magnitude += abs(value)

    def matches(self, other: Tally, rtol: float = 1e-6) -> bool:
        return self.count == other.count and abs(self.total - other.total) <= rtol * max(
            self.magnitude, other.magnitude, 1.0
        )

    def __repr__(self) -> str:
        return f"Tally(count={self.count}, total={self.total:.6g})"


def touch(x, tally: Tally) -> None:
    """Sum `x`'s numeric content into `tally`."""
    import numbers

    import numpy as np
    import pandas as pd

    if x is None or isinstance(x, (str, bytes, bool)):
        return
    if isinstance(x, numbers.Number):
        tally.add_scalar(x)
    elif isinstance(x, np.ndarray):
        if x.dtype.names:
            for n in x.dtype.names:
                touch(x[n], tally)
        elif x.dtype.kind in "biuf":
            tally.add(x)
        elif x.dtype.kind == "O":
            for v in x.ravel():
                touch(v, tally)
    elif isinstance(x, pd.DataFrame):
        tally.add(x.select_dtypes("number").to_numpy())
        for c in x.columns:
            if x[c].dtype == object:
                for v in x[c]:
                    touch(v, tally)
    elif hasattr(x, "values") and hasattr(x, "dims"):  # xarray
        touch(x.values, tally)
    elif isinstance(x, dict):
        for v in x.values():
            touch(v, tally)
    elif isinstance(x, (list, tuple)):
        for v in x:
            touch(v, tally)


def materialize_flopy3(sim) -> Tally:
    """Fetch every array and list dataset of every loaded package, and sum it.

    `MFArray`/`MFTransientArray`/`MFList`/`MFTransientList` via `get_data()`;
    pandas-backed lists via `get_dataframe()`, the native form (`get_data()`
    would add a DataFrame -> recarray conversion). Scalars aren't touched;
    they're always parsed at load. This is what reads ``OPEN/CLOSE`` arrays.
    """
    from flopy.mf6.data.mfdataarray import MFArray
    from flopy.mf6.data.mfdatalist import MFList
    from flopy.mf6.data.mfdataplist import MFPandasList

    packages = list(sim.sim_package_list)
    for name in sim.model_names:
        packages.extend(sim.get_model(name).packagelist)
    tally = Tally()
    for package in packages:
        for block in package.blocks.values():
            for dataset in block.datasets.values():
                if isinstance(dataset, MFPandasList):
                    touch(dataset.get_dataframe(), tally)
                elif isinstance(dataset, (MFArray, MFList)):
                    touch(dataset.get_data(), tally)
    return tally


def materialize_flopy4(sim) -> Tally:
    """Walk the component tree and sum every numeric value held.

    flopy4 holds everything in memory after load, so this reads no files;
    it's here so both libraries' ``load + materialize`` touch their data."""
    import attrs

    from flopy4.mf6.component import Component

    tally = Tally()
    seen: set[int] = set()
    # write_context holds formatting (IPRN, FACTOR, ...), not data
    skip = ("_parent", "parent", "workspace", "filename", "write_context")

    def walk(obj) -> None:
        if id(obj) in seen:
            return
        seen.add(id(obj))
        items = dict(vars(obj)) if hasattr(obj, "__dict__") else {}
        if attrs.has(type(obj)):  # slotted records have no __dict__
            for f in attrs.fields(type(obj)):
                if f.name not in items and hasattr(obj, f.name):
                    items[f.name] = getattr(obj, f.name)
        for k, v in items.items():
            if k not in skip:
                value(v)
        if isinstance(obj, Component):
            for child in obj._children.values():
                walk(child)

    def value(v) -> None:
        if isinstance(v, Component) or (attrs.has(type(v)) and not isinstance(v, type)):
            walk(v)
        elif isinstance(v, dict):
            for x in v.values():
                value(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                value(x)
        else:
            touch(v, tally)

    walk(sim)
    return tally


def write_flopy3(sim, out: Path) -> None:
    sim.set_sim_path(str(out))
    sim.write_simulation(silent=True)


def write_flopy4(sim, out: Path) -> None:
    sim.workspace = Path(out)
    sim.write()


def load(library: str, ws: Path, load_only: list[str] | None = None):
    if library == "flopy3":
        return load_flopy3(ws, load_only)
    return load_flopy4(ws)


def materialize(library: str, sim) -> Tally:
    if library == "flopy3":
        return materialize_flopy3(sim)
    return materialize_flopy4(sim)


def write(library: str, sim, out: Path) -> None:
    """Write `sim` into `out`, an empty directory."""
    if library == "flopy3":
        write_flopy3(sim, out)
    else:
        write_flopy4(sim, out)


def import_library(library: str) -> None:
    if library == "flopy3":
        import flopy  # noqa: F401
    else:
        import flopy4.mf6.simulation  # noqa: F401
