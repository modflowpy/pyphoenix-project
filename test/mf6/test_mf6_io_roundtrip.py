"""
Round-trip IO test: load -> write -> reload, then check for equivalence.
Also include a few specific tests for known gaps in the loader, which are
not caught by the round-trip tests.
"""

import math
import warnings
from collections.abc import Mapping
from pathlib import Path

import attrs
import numpy as np
import pytest
import xarray as xr
from modflow_devtools.models import copy_to

from flopy4.mf6.component import Component
from flopy4.mf6.gwe import Adv as GweAdv
from flopy4.mf6.gwe import Dis as GweDis
from flopy4.mf6.gwe import Est as GweEst
from flopy4.mf6.gwe import Gwe, Mwe, Sfe, Uze
from flopy4.mf6.gwe import Ic as GweIc
from flopy4.mf6.gwe import Ssm as GweSsm
from flopy4.mf6.gwf import Dis, Ghb, Gwf, Ic, Npf, Oc, Wel
from flopy4.mf6.gwt import Dis as GwtDis
from flopy4.mf6.gwt import Gwt, Mwt, Sft, Uzt
from flopy4.mf6.gwt import Ic as GwtIc
from flopy4.mf6.gwt import Mst as GwtMst
from flopy4.mf6.gwt import Ssm as GwtSsm
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.time import Time
from flopy4.mf6.utl.obs import Obs

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


def test_tas_period_array_kept(tmp_path):
    """A `TIMEARRAYSERIES` reference in a READASARRAYS period block survives."""
    _, _, out = _roundtrip(tmp_path, "mf6/test/test027_TimeseriesTest")
    # source: `RECHARGE  TimeArraySeries  RchSeries`
    block = _period_block(out, "readasarrays")
    assert "timearrayseries" in block and "rchseries" in block


def test_repeated_ts6_kept(tmp_path):
    """Every `TS6 FILEIN` row in a package's options is kept."""
    # `alt_model` isn't referenced from mfsim.nam, so load the WEL directly
    workspace = copy_to(tmp_path, "mf6/test/test106_tsnodata", verbose=False)
    wel = Wel.load(workspace / "alt_model" / "model.wel")
    loaded = {Path(ts.filename).name for ts in wel.ts}
    expected = {f"model_well{i}_pump.ts" for i in range(1, 6)}
    assert expected <= loaded


def test_tvk_child_kept(tmp_path):
    """NPF's TVK6 file loads as a child and is written back."""
    workspace = copy_to(tmp_path / "source", "mf6/test/test001a_Tharmonic", verbose=False)
    npf = workspace / "flow15.npf"
    npf.write_text(npf.read_text().replace("SAVE_FLOWS", "SAVE_FLOWS\n  TVK6 FILEIN flow15.tvk"))
    (workspace / "flow15.tvk").write_text(
        "BEGIN PERIOD 1\n  1 1 3 K 5.0\n  1 1 4 K33 2.5\nEND PERIOD\n"
    )
    sim = Simulation.load(workspace / "mfsim.nam")
    tvk = sim["flow15"].npf.tvk
    rows = tvk.stress_period_data[0]
    settings = [(type(r.tvksetting).__name__, r.cellid) for r in rows]
    assert settings == [("K", (0, 0, 2)), ("K33", (0, 0, 3))]
    assert (rows[0].tvksetting.k, rows[1].tvksetting.k33) == (5.0, 2.5)

    out = tmp_path / "written"
    out.mkdir()
    sim.workspace = out
    sim.write()
    assert "TVK6 FILEIN flow15.tvk" in (out / "flow15.npf").read_text()
    reloaded = Simulation.load(out / "mfsim.nam")
    diffs: list[str] = []
    _diff(rows, reloaded["flow15"].npf.tvk.stress_period_data[0], "tvk", diffs)
    assert not diffs, "\n".join(diffs)


def test_tvs_child_kept(tmp_path):
    """STO's TVS6 file loads as a child and is written back."""
    workspace = copy_to(tmp_path / "source", "mf6/test/test003_gwfs_tr", verbose=False)
    sto = workspace / "model.sto"
    sto.write_text(sto.read_text().replace("SAVE_FLOWS", "SAVE_FLOWS\n  TVS6 FILEIN model.tvs"))
    (workspace / "model.tvs").write_text(
        "BEGIN PERIOD 2\n  1 1 1 SS 2.0e-5\n  1 1 2 SY 0.1\nEND PERIOD\n"
    )
    sim = Simulation.load(workspace / "mfsim.nam")
    rows = sim["GWF_1"].sto.tvs.stress_period_data[1]
    settings = [(type(r.tvssetting).__name__, r.cellid) for r in rows]
    assert settings == [("Ss", (0, 0, 0)), ("Sy", (0, 0, 1))]
    assert (rows[0].tvssetting.ss, rows[1].tvssetting.sy) == (2.0e-5, 0.1)

    out = tmp_path / "written"
    out.mkdir()
    sim.workspace = out
    sim.write()
    assert "TVS6 FILEIN model.tvs" in (out / "model.sto").read_text()
    reloaded = Simulation.load(out / "mfsim.nam")
    diffs: list[str] = []
    _diff(rows, reloaded["GWF_1"].sto.tvs.stress_period_data[1], "tvs", diffs)
    assert not diffs, "\n".join(diffs)


def test_readarray_non_layered_grid_arrays():
    """A grid package array given without LAYERED covers all nodes."""
    from flopy4.mf6.converter.ingress.structure import _parse_readarray_period_block
    from flopy4.mf6.gwf import Welg
    from flopy4.mf6.load_context import LoadContext

    fields = attrs.fields_dict(Welg)
    lookup = {"q": fields["q"], "a1": fields["aux"], "a2": fields["aux"]}
    rows = [
        ["q", "LAYERED"],
        ["INTERNAL"],
        ["1.0", "2.0", "3.0"],
        ["INTERNAL"],
        ["4.0", "5.0", "6.0"],
        ["a1"],
        ["INTERNAL"],
        ["1.0", "1.0", "1.0"],
        ["1.0", "1.0", "1.0"],
        ["a2"],
        ["INTERNAL"],
        ["0.5", "0.5", "0.5"],
        ["0.5", "0.5", "0.5"],
    ]
    result = _parse_readarray_period_block(rows, lookup, {"nlay": 2, "nodes": 6}, LoadContext())
    assert np.array_equal(result["q"], [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    assert np.array_equal(result["a1"], np.ones((2, 3)))
    assert np.array_equal(result["a2"], np.full((2, 3), 0.5))


def test_grid_package_aux_keeps_package_name(tmp_path):
    """A grid package's aux arrays don't replace its name."""
    from flopy4.mf6.gwf import Chdg, Dis
    from flopy4.mf6.load_context import LoadContext

    path = tmp_path / "model.chdg"
    path.write_text(
        "BEGIN OPTIONS\n  READARRAYGRID\n  AUXILIARY temperature\nEND OPTIONS\n\n"
        "BEGIN PERIOD 1\n  head\n    CONSTANT 1.0\n  temperature\n    CONSTANT 5.0\n"
        "END PERIOD 1\n"
    )
    dis = Dis(nlay=1, nrow=1, ncol=2)
    context = LoadContext(workspace=tmp_path, dims=dis.get_dims())
    chd = Chdg.load(path, name="chd-1", context=context)
    assert chd.name == "chd-1"
    assert np.allclose(np.asarray(chd.aux[0]["temperature"]), 5.0)


def test_auxiliary_option_keeps_all_names(tmp_path):
    """Every AUXILIARY name loads (numpy >= 2.5 changed NDArray's origin)."""
    from flopy4.mf6.gwf import Welg

    path = tmp_path / "model.welg"
    path.write_text("BEGIN OPTIONS\n  READARRAYGRID\n  AUXILIARY a1 a2\nEND OPTIONS\n")
    assert list(Welg.load(path, name="wel").auxiliary) == ["a1", "a2"]


def test_open_close_reads_only_needed_values(tmp_path):
    """An OPEN/CLOSE array reads only the values it needs, as in MF6."""
    from flopy4.mf6.converter.ingress.structure import _read_control_record
    from flopy4.mf6.load_context import LoadContext

    (tmp_path / "values.txt").write_text("1.0 2.0 3.0 4.0 5.0\n")
    rows = [["OPEN/CLOSE", "values.txt"]]
    values, i = _read_control_record(rows, 0, LoadContext(workspace=tmp_path), np.float64, 3)
    assert np.array_equal(values, [1.0, 2.0, 3.0]) and i == 1


def test_layered_open_close_griddata(tmp_path):
    """A LAYERED array reads one OPEN/CLOSE file per layer, each only its
    layer's values."""
    from flopy4.mf6.converter.ingress.structure import _parse_array_block
    from flopy4.mf6.gwf import Npf
    from flopy4.mf6.load_context import LoadContext

    (tmp_path / "k1.txt").write_text("1.0 2.0 3.0\n")
    (tmp_path / "k2.txt").write_text("4.0 5.0 6.0 7.0 8.0\n")
    rows = [["k", "LAYERED"], ["OPEN/CLOSE", "k1.txt"], ["OPEN/CLOSE", "k2.txt"]]
    fields = {"k": attrs.fields_dict(Npf)["k"]}
    context = LoadContext(workspace=tmp_path)
    result = _parse_array_block(rows, fields, {"nlay": 2, "nodes": 6}, context)
    assert np.array_equal(result["k"], [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])


@pytest.mark.parametrize("pkg_cls", [Sft, Mwt, Uzt])
def test_gwt_transport_round_trips(tmp_path, pkg_cls):
    """GWT's advanced transport packages (sft, mwt, uzt -- registered the
    same way) round-trip load -> write -> reload."""
    gwt_name = "gwt1"
    sim = Simulation(
        tdis=Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="DAYS"),
        workspace=tmp_path,
        name="sim1",
        solutiongroup=[Ims(filename="gwt.ims", models=[gwt_name])],
    )
    dis = GwtDis(nlay=1, nrow=1, ncol=2, delr=1.0, delc=1.0, top=1.0, botm=0.0)
    gwt = Gwt(parent=sim, dis=dis, name=gwt_name)
    GwtIc(parent=gwt, strt=0.0)
    GwtMst(parent=gwt, porosity=0.3)
    GwtSsm(parent=gwt)
    pkg = pkg_cls(
        parent=gwt,
        dims={"nper": 1},
        boundnames=True,
        packagedata=[(0, 1.0, "reach1")],
        stress_period_data={0: [[0, "STATUS", "CONSTANT"], [0, "CONCENTRATION", 5.0]]},
        name=f"{pkg_cls.__name__.upper()}-1",
    )

    sim.write()
    reloaded = Simulation.load(tmp_path / "mfsim.nam")
    field = pkg_cls.__name__.lower()
    diffs: list[str] = []
    _diff(pkg.packagedata, getattr(reloaded[gwt_name], field)[0].packagedata, field, diffs)
    assert not diffs, "\n".join(diffs)


@pytest.mark.parametrize(
    "pkg_cls, row",
    [
        (Sfe, (0, 1.0, 0.1, 0.01, "reach1")),
        (Uze, (0, 1.0, "reach1")),
        (Mwe, (0, 1.0, 0.1, 0.1, "reach1")),
    ],
)
def test_gwe_transport_round_trips(tmp_path, pkg_cls, row):
    """GWE's advanced transport packages (sfe, uze, mwe -- registered the
    same way) round-trip load -> write -> reload."""
    gwe_name = "gwe1"
    sim = Simulation(
        tdis=Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="DAYS"),
        workspace=tmp_path,
        name="sim1",
        solutiongroup=[Ims(filename="gwe.ims", models=[gwe_name])],
    )
    dis = GweDis(nlay=1, nrow=1, ncol=2, delr=1.0, delc=1.0, top=1.0, botm=0.0)
    gwe = Gwe(parent=sim, dis=dis, name=gwe_name)
    GweIc(parent=gwe, strt=0.0)
    GweAdv(parent=gwe, scheme="UPSTREAM")
    GweEst(parent=gwe, porosity=0.3, heat_capacity_solid=800.0, density_solid=2700.0)
    GweSsm(parent=gwe)
    pkg = pkg_cls(
        parent=gwe,
        dims={"nper": 1},
        boundnames=True,
        packagedata=[row],
        stress_period_data={0: [[0, "STATUS", "CONSTANT"], [0, "TEMPERATURE", 20.0]]},
        name=f"{pkg_cls.__name__.upper()}-1",
    )

    sim.write()
    reloaded = Simulation.load(tmp_path / "mfsim.nam")
    field = pkg_cls.__name__.lower()
    diffs: list[str] = []
    _diff(pkg.packagedata, getattr(reloaded[gwe_name], field)[0].packagedata, field, diffs)
    assert not diffs, "\n".join(diffs)


def test_quoted_multiword_boundname_and_obsname_round_trips(tmp_path):
    """A multi-word boundname and its obsname/id survive load -> write ->
    reload as one token, not split at the embedded space."""
    gwf_name = "gwf1"
    sim = Simulation(
        tdis=Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="DAYS"),
        workspace=tmp_path,
        name="sim1",
        solutiongroup=[Ims(filename="gwf.ims", models=[gwf_name])],
    )
    dis = Dis(nlay=1, nrow=1, ncol=2, delr=1.0, delc=1.0, top=1.0, botm=0.0)
    gwf = Gwf(parent=sim, dis=dis, name=gwf_name, save_flows=True)
    Ic(parent=gwf, strt=0.0)
    Npf(parent=gwf, icelltype=0, k=1.0)
    Oc(parent=gwf, head_file=f"{gwf_name}.hds", budget_file=f"{gwf_name}.cbc")
    ghb = Ghb(
        parent=gwf,
        boundnames=True,
        stress_period_data={0: [[(0, 0, 0), 1.0, 10.0, "my bound"]]},
        name="GHB-1",
    )
    Obs(
        parent=ghb,
        continuous=[
            Obs.ContinuousBlock(
                output=Obs.Output(obs_output_file_name=f"{gwf_name}.ghb.obs.csv"),
                continuous=[Obs.Continuous(obsname="my obs", obstype="GHB", id_="my bound")],
            )
        ],
        name="obs",
    )

    sim.write()
    reloaded = Simulation.load(tmp_path / "mfsim.nam")
    rghb = reloaded[gwf_name].ghb[0]
    assert rghb.stress_period_data[0][0].boundname == "my bound"
    robs = rghb.obs.continuous[0].continuous[0]
    assert (robs.obsname, robs.id_) == ("my obs", "my bound")


@pytest.mark.parametrize(
    "boundname, warns",
    [("5", True), ("1.50", True), ("1d0", True), ("b5", False), ("inf", False)],
)
def test_obs_id_naming_numeric_boundname_warns(tmp_path, boundname, warns):
    """MF6 may read an observation's id that looks like a number as a
    cell, not a boundname, so writing one warns."""
    sim = Simulation(
        tdis=Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="DAYS"),
        workspace=tmp_path,
        name="sim1",
        solutiongroup=[Ims(filename="gwf.ims", models=["gwf1"])],
    )
    dis = Dis(nlay=1, nrow=1, ncol=2, delr=1.0, delc=1.0, top=1.0, botm=0.0)
    gwf = Gwf(parent=sim, dis=dis, name="gwf1", save_flows=True)
    Ic(parent=gwf, strt=0.0)
    Npf(parent=gwf, icelltype=0, k=1.0)
    ghb = Ghb(
        parent=gwf,
        boundnames=True,
        stress_period_data={0: [[(0, 0, 0), 1.0, 10.0, boundname]]},
        name="GHB-1",
    )
    Obs(
        parent=ghb,
        continuous=[
            Obs.ContinuousBlock(
                output=Obs.Output(obs_output_file_name="gwf1.ghb.obs.csv"),
                continuous=[Obs.Continuous(obsname="o", obstype="GHB", id_=boundname)],
            )
        ],
        name="obs",
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        sim.write()
    messages = [str(w.message) for w in caught if "MF6 may read as a cell" in str(w.message)]
    assert len(messages) == warns


def _ghb_sim(tmp_path, rows, *, auxiliary=None, obs=()):
    """A one-row-of-cells GHB model with boundnames, and an OBS file of
    (obsname, id) observations of it."""
    gwf_name = "gwf1"
    sim = Simulation(
        tdis=Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="DAYS"),
        workspace=tmp_path,
        name="sim1",
        solutiongroup=[Ims(filename="gwf.ims", models=[gwf_name])],
    )
    dis = Dis(nlay=1, nrow=1, ncol=len(rows), delr=1.0, delc=1.0, top=1.0, botm=0.0)
    gwf = Gwf(parent=sim, dis=dis, name=gwf_name)
    Ic(parent=gwf, strt=0.0)
    Npf(parent=gwf, icelltype=0, k=1.0)
    Oc(parent=gwf)
    kwargs = {"auxiliary": auxiliary} if auxiliary else {}
    ghb = Ghb(
        parent=gwf,
        boundnames=True,
        stress_period_data={0: [[(0, 0, j), 1.0, 10.0, *row] for j, row in enumerate(rows)]},
        name="GHB-1",
        **kwargs,
    )
    if obs:
        Obs(
            parent=ghb,
            continuous=[
                Obs.ContinuousBlock(
                    output=Obs.Output(obs_output_file_name=f"{gwf_name}.ghb.obs.csv"),
                    continuous=[
                        Obs.Continuous(obsname=name, obstype="GHB", id_=id_) for name, id_ in obs
                    ],
                )
            ],
            name="obs",
        )
    return sim, ghb


def _reloaded_ghb(tmp_path):
    return Simulation.load(tmp_path / "mfsim.nam")["gwf1"].ghb[0]


@pytest.mark.parametrize("boundname", ["5", "end", "begin", "endpoint", None])
@pytest.mark.parametrize("aux", [(), (3.0,)], ids=["no-aux", "aux"])
def test_boundname_round_trips(tmp_path, boundname, aux):
    """A boundname is whatever follows a row's other columns, as MF6 reads
    it, so one that looks like a number or a block keyword survives write
    -> reload as written."""
    sim, ghb = _ghb_sim(tmp_path, [(aux, boundname), (aux, "b")], auxiliary=["x"] if aux else None)
    sim.write()
    rows = _reloaded_ghb(tmp_path).stress_period_data[0]
    assert [(r.boundname, r.aux) for r in rows] == [(boundname, aux), ("b", aux)]


def test_empty_boundname_is_none(tmp_path):
    """An empty boundname is no boundname, however the row gives it."""
    sim, ghb = _ghb_sim(tmp_path, [("",), ((), ""), ("b",)])
    assert [r.boundname for r in ghb.stress_period_data[0]] == [None, None, "b"]
    sim.write()
    rows = _reloaded_ghb(tmp_path).stress_period_data[0]
    assert [r.boundname for r in rows] == [None, None, "b"]


def test_hand_written_boundnames_load(tmp_path):
    """Boundnames in a file written elsewhere load by position, whatever
    their text."""
    sim, _ = _ghb_sim(tmp_path, [((3.0,), "b")] * 5, auxiliary=["x"])
    sim.write()
    ghb_file = next(tmp_path.glob("*.ghb"))
    rows = """\
  1 1 1 1.0 10.0 3.0 5
  1 1 2 1.0 10.0 3.0 '1.50'
  1 1 3 1.0 10.0 3.0 end
  1 1 4 1.0 10.0 3.0 ''
  1 1 5 1.0 10.0 3.0
"""
    text = ghb_file.read_text()
    start = text.index("BEGIN PERIOD 1\n") + len("BEGIN PERIOD 1\n")
    ghb_file.write_text(text[:start] + rows + text[text.index("END PERIOD") :])

    rghb = _reloaded_ghb(tmp_path)
    rows_back = rghb.stress_period_data[0]
    assert [r.boundname for r in rows_back] == ["5", "1.50", "end", None, None]
    assert all(r.aux == (3.0,) for r in rows_back)
