"""
Round-trip IO test: load -> write -> reload, then check for equivalence.
Also include a few specific tests for known gaps in the loader, which are
not caught by the round-trip tests.
"""

import math
from collections.abc import Mapping
from pathlib import Path

import attrs
import numpy as np
import pytest
import xarray as xr
from modflow_devtools.models import copy_to

from flopy4.mf6.component import Component
from flopy4.mf6.gwf import Wel
from flopy4.mf6.simulation import Simulation

from .test_mf6_load_all_models import KNOWN_PASSING

# cause -> models expected to fail the roundtrip
XFAIL: dict[str, set[str]] = {}

MODELS = sorted(m for m in KNOWN_PASSING if not m.startswith("mf6/large/"))


def _param(model_name):
    causes = [cause for cause, models in XFAIL.items() if model_name in models]
    marks = [pytest.mark.xfail(reason="; ".join(causes), strict=True)] if causes else []
    return pytest.param(model_name, marks=marks)


def _is_children(value):
    if isinstance(value, Component):
        return True
    if isinstance(value, Mapping):
        return bool(value) and all(isinstance(v, Component) for v in value.values())
    if isinstance(value, (list, tuple)):
        return bool(value) and all(isinstance(v, Component) for v in value)
    return False


def _diff(a, b, path, out):
    """Append a line to `out` for each difference between values `a` and `b`."""
    if isinstance(a, xr.DataArray):
        a = a.values
    if isinstance(b, xr.DataArray):
        b = b.values
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        a, b = np.asarray(a), np.asarray(b)
        # a constant array may load 0-d on one side and broadcast on the other
        if a.shape != b.shape and (a.ndim == 0 or b.ndim == 0):
            a, b = np.broadcast_arrays(a, b)
        if a.shape != b.shape:
            out.append(f"{path}: shape {a.shape} != {b.shape}")
            return
        try:
            equal = np.array_equal(a, b, equal_nan=a.dtype.kind == "f")
        except TypeError:
            equal = np.array_equal(a, b)
        if not equal:
            out.append(f"{path}: array values differ")
        return
    if attrs.has(type(a)) and not isinstance(a, Component):
        if type(a) is not type(b):
            out.append(f"{path}: type {type(a).__name__} != {type(b).__name__}")
            return
        for f in attrs.fields(type(a)):
            if f.name not in ("parent", "_parent"):
                _diff(getattr(a, f.name), getattr(b, f.name), f"{path}.{f.name}", out)
        return
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f"{path}[{k!r}]: only in {'loaded' if k in a else 'reloaded'}")
            else:
                _diff(a[k], b[k], f"{path}[{k!r}]", out)
        return
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            out.append(f"{path}: len {len(a)} != {len(b)}")
            return
        for i, (x, y) in enumerate(zip(a, b)):
            _diff(x, y, f"{path}[{i}]", out)
        return
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return
    if isinstance(a, Path) or isinstance(b, Path):
        a, b = str(a), str(b)
    # MF6 input is case-insensitive
    if isinstance(a, str) and isinstance(b, str):
        a, b = a.lower(), b.lower()
    if a != b:
        out.append(f"{path}: {a!r:.60} != {b!r:.60}")


def _diff_components(a, b, path, out):
    """Compare block fields of two component trees, recursing into children."""
    if type(a) is not type(b):
        out.append(f"{path}: {type(a).__name__} != {type(b).__name__}")
        return
    for f in attrs.fields(type(a)):
        if f.name in ("filename", "workspace", "name") or f.name.startswith("_"):
            continue
        if not f.metadata.get("block"):
            continue
        va, vb = getattr(a, f.name, None), getattr(b, f.name, None)
        if _is_children(va) or _is_children(vb):
            continue
        _diff(va, vb, f"{path}.{f.name}", out)
    ca, cb = dict(a._children), dict(b._children)
    for k in sorted(set(ca) | set(cb)):
        if k not in ca or k not in cb:
            out.append(f"{path}/{k}: child only in {'loaded' if k in ca else 'reloaded'}")
        else:
            _diff_components(ca[k], cb[k], f"{path}/{k}", out)


def _roundtrip(tmp_path, model_name):
    """Load a corpus model, write it to a fresh workspace, and reload it."""
    workspace = copy_to(tmp_path / "source", model_name, verbose=False)
    sim = Simulation.load(workspace / "mfsim.nam")
    out = tmp_path / "written"
    out.mkdir()
    sim.workspace = out
    sim.write()
    return sim, Simulation.load(out / "mfsim.nam"), out


@pytest.mark.parametrize("model_name", [_param(m) for m in MODELS])
def test_roundtrip(tmp_path, model_name):
    loaded, reloaded, _ = _roundtrip(tmp_path, model_name)
    diffs = []
    _diff_components(loaded, reloaded, "sim", diffs)
    assert not diffs, "\n".join(diffs)


def _period_block(workspace, text):
    """Return the lowercased period 1 block of the file containing `text`,
    or "" if that file has none."""
    for path in workspace.iterdir():
        content = path.read_text().lower() if path.is_file() else ""
        if text in content:
            _, found, rest = content.partition("begin period 1")
            return rest.partition("end period")[0] if found else ""
    raise AssertionError(f"no written file contains {text!r}")


def test_aux_period_array_kept(tmp_path):
    """An `AUXILIARY`-named array in a READASARRAYS period block survives."""
    _, _, out = _roundtrip(tmp_path, "mf6/test/test027_TimeseriesTest")
    # source: `Auxarray1` / `constant 2.3`
    assert "auxarray1" in _period_block(out, "readasarrays")


@pytest.mark.xfail(reason="missing TAS period arrays", strict=True)
def test_tas_period_array_kept(tmp_path):
    """A `TIMEARRAYSERIES` reference in a READASARRAYS period block survives."""
    _, _, out = _roundtrip(tmp_path, "mf6/test/test027_TimeseriesTest")
    # source: `RECHARGE  TimeArraySeries  RchSeries`
    block = _period_block(out, "readasarrays")
    assert "timearrayseries" in block and "rchseries" in block


def _strings(value):
    """Yield every str/Path nested in `value`, as a str."""
    if isinstance(value, (str, Path)):
        yield str(value)
    elif isinstance(value, Mapping):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)
    elif attrs.has(type(value)) and not isinstance(value, Component):
        for f in attrs.fields(type(value)):
            yield from _strings(getattr(value, f.name))


def test_repeated_ts6_kept(tmp_path):
    """Every `TS6 FILEIN` row in a package's options is kept."""
    # `alt_model` isn't referenced from mfsim.nam, so load the WEL directly
    workspace = copy_to(tmp_path, "mf6/test/test106_tsnodata", verbose=False)
    wel = Wel.load(workspace / "alt_model" / "model.wel")
    loaded = {
        Path(s).name
        for f in attrs.fields(Wel)
        if f.metadata.get("block") == "options"
        for s in _strings(getattr(wel, f.name))
    }
    expected = {f"model_well{i}_pump.ts" for i in range(1, 6)}
    assert expected <= loaded
