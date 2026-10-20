"""Tests for recursive namefile loading (Simulation.load()/Gwf.load()).

Builds a small Gwf model via the existing, working Python construction API
(mirroring docs/examples/quickstart.py), writes it with the existing,
working egress path, then loads it back and checks the tree was resolved
correctly: dis attached (with the right model-scoped class), dims threaded
into npf's griddata shapes, chd's list-input round-tripped, and ims
attached under the simulation's solutiongroup.
"""

from pathlib import Path

import numpy as np
import pytest
from flopy.discretization.structuredgrid import StructuredGrid

from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.time import Time


@pytest.fixture()
def written_sim(tmp_path):
    """Write a small one-layer 10x10 Gwf model + Ims solution to tmp_path,
    matching docs/examples/quickstart.py, and return the workspace path."""
    workspace = tmp_path / "namefile_load"
    workspace.mkdir()

    grid = StructuredGrid(
        nlay=1,
        nrow=10,
        ncol=10,
        delr=1.0 * np.ones(10),
        delc=1.0 * np.ones(10),
        top=1.0 * np.ones((10, 10)),
        botm=0.0 * np.ones((1, 10, 10)),
    )

    sim = Simulation(name="qs", workspace=workspace, tdis=Time(perlen=[1.0], nstp=[1]))
    gwf_name = "mymodel"
    Ims(
        parent=sim,
        models=[gwf_name],
        outer_dvclose=1e-3,
        outer_maximum=25,
        inner_maximum=50,
        inner_dvclose=1e-3,
        rclose=Ims.Rclose(inner_rclose=0.1),
        linear_acceleration="cg",
    )
    gwf = Gwf(parent=sim, name=gwf_name, save_flows=True, dis=grid)
    gwf.npf = Npf(print_flows=True, save_flows=True, save_specific_discharge=True)
    Chd(parent=gwf, stress_period_data={0: [((0, 0, 0), 1.0), ((0, 9, 9), 0.0)]})
    gwf.ic = Ic(strt=1.0)
    gwf.oc = Oc(
        budget_file=f"{gwf.name}.bud",
        head_file=f"{gwf.name}.hds",
        stress_period_data={0: [("SAVE", "HEAD", "ALL"), ("SAVE", "BUDGET", "ALL")]},
    )
    sim.write()
    return workspace


def test_load_simulation_resolves_model_and_solution(written_sim):
    loaded = Simulation.load(written_sim / "mfsim.nam")

    assert len(loaded.models) == 1
    gwf = next(iter(loaded.models))
    assert isinstance(gwf, Gwf)

    assert len(loaded.solutiongroup) == 1
    ims = next(iter(loaded.solutiongroup))
    assert isinstance(ims, Ims)
    assert ims.models == ["mymodel"]


def test_load_simulation_resolves_dis_and_dims(written_sim):
    gwf = next(iter(Simulation.load(written_sim / "mfsim.nam").models))

    assert isinstance(gwf.dis, Dis)
    assert gwf.dis.get_dims() == {
        "nlay": 1,
        "nrow": 10,
        "ncol": 10,
        "nodes": 100,
        "ncpl": 100,
        "ncelldim": 3,
    }


def test_load_simulation_propagates_dims_to_griddata_siblings(written_sim):
    """Npf's griddata arrays need dims resolved from the dis sibling loaded
    moments earlier in the same "packages" block -- the dims-provider-first
    ordering _resolve_bindings implements."""
    gwf = next(iter(Simulation.load(written_sim / "mfsim.nam").models))

    assert isinstance(gwf.npf, Npf)
    assert gwf.npf.k.shape == (100,)
    assert np.all(gwf.npf.k == 1.0)

    assert isinstance(gwf.ic, Ic)
    assert gwf.ic.strt.shape == (100,)
    assert np.all(gwf.ic.strt == 1.0)


def test_load_simulation_resolves_list_package_rows(written_sim):
    gwf = next(iter(Simulation.load(written_sim / "mfsim.nam").models))

    assert len(gwf.chd) == 1
    chd = gwf.chd[0]
    assert isinstance(chd, Chd)
    rows = chd.stress_period_data[0]
    assert [(r.cellid, r.head) for r in rows] == [((0, 0, 0), 1.0), ((0, 9, 9), 0.0)]


def test_load_gwf_directly(written_sim):
    """A model can also be loaded on its own, not just recursively via its
    simulation -- Gwf.load() resolves its own "packages" block bindings the
    same way, dims included."""
    gwf = Gwf.load(written_sim / "mymodel.nam")

    assert isinstance(gwf.dis, Dis)
    assert gwf.npf.k.shape == (100,)
    assert len(gwf.chd) == 1


def test_load_preserves_model_pname(tmp_path):
    """A model's custom pname round-trips via the child's own `.name`:
    the namefile row's pname, not the referenced file's name, which the
    row's pname needn't match. See `test_load_preserves_list_package_pname`
    below for the same round trip on a model's package."""
    import numpy as np
    from flopy.discretization.structuredgrid import StructuredGrid

    workspace = tmp_path / "pname"
    workspace.mkdir()
    grid = StructuredGrid(
        nlay=1,
        nrow=2,
        ncol=2,
        delr=1.0 * np.ones(2),
        delc=1.0 * np.ones(2),
        top=1.0 * np.ones((2, 2)),
        botm=0.0 * np.ones((1, 2, 2)),
    )
    sim = Simulation(name="sim", workspace=workspace, tdis=Time(perlen=[1.0], nstp=[1]))
    Gwf(parent=sim, name="a_custom_model_name", dis=grid)
    sim.write()

    loaded = Simulation.load(workspace / "mfsim.nam")

    assert [m.name for m in loaded.models] == ["a_custom_model_name"]
    gwf = loaded["a_custom_model_name"]
    assert gwf.name == "a_custom_model_name"


def test_load_preserves_list_package_pname(written_sim):
    """A list-kind package field's real pname (a namefile packages-block
    row's third term) survives a load -> write round trip: the child's own
    `.name` preserves an explicitly-given name directly.
    """
    nam_path = written_sim / "mymodel.nam"
    nam_path.write_text(
        nam_path.read_text().replace("CHD6 mymodel.chd chd0", "CHD6 mymodel.chd boundary_west")
    )

    gwf = next(iter(Simulation.load(written_sim / "mfsim.nam").models))
    chd = gwf.chd[0]
    assert isinstance(chd, Chd)
    assert chd.name == "boundary_west"

    gwf.write()
    rewritten = (written_sim / "mymodel.nam").read_text()
    assert "CHD6 mymodel.chd boundary_west" in rewritten


def test_load_disambiguates_ga_variant(tmp_path):
    """Real MF6 writes "CHD6" for both Chd and Chdg (see
    component_ftype()'s docstring) -- the namefile row alone can't tell
    them apart, so _resolve_bindings must peek the referenced file's own
    OPTIONS block for the READARRAYGRID marker."""
    import textwrap

    (tmp_path / "model.dis").write_text(
        textwrap.dedent("""\
            BEGIN OPTIONS
            END OPTIONS
            BEGIN DIMENSIONS
              NLAY 1
              NROW 2
              NCOL 2
            END DIMENSIONS
            BEGIN GRIDDATA
              DELR
                CONSTANT 1.0
              DELC
                CONSTANT 1.0
              TOP
                CONSTANT 1.0
              BOTM
                CONSTANT 0.0
            END GRIDDATA
        """)
    )
    (tmp_path / "model.chdg").write_text(
        textwrap.dedent("""\
            BEGIN OPTIONS
              READARRAYGRID
            END OPTIONS
            BEGIN PERIOD 1
             HEAD LAYERED
              CONSTANT 1.0
            END PERIOD 1
        """)
    )
    (tmp_path / "model.nam").write_text(
        textwrap.dedent("""\
            BEGIN PACKAGES
             DIS6 model.dis dis
             CHD6 model.chdg chdg0
            END PACKAGES
        """)
    )

    gwf = Gwf.load(tmp_path / "model.nam")

    from flopy4.mf6.gwf.chdg import Chdg

    assert len(gwf.chd) == 1
    assert isinstance(gwf.chd[0], Chdg)


def test_load_exchange_between_grids(tmp_path):
    """An exchange's cellids each take their own model's grid width: a
    DIS (3) model and a DISV (2) one, including the exchange's GNC."""
    from flopy4.mf6.exg.gwfgwf import Gwfgwf
    from flopy4.mf6.gwf import Disv, Gnc

    sim = Simulation(name="mx", workspace=tmp_path, tdis=Time(perlen=[1.0], nstp=[1]))
    Gwf(
        parent=sim,
        name="a",
        dis=Dis(nlay=1, nrow=2, ncol=2, delr=1.0, delc=1.0, top=1.0, botm=0.0),
    )
    Gwf(
        parent=sim,
        name="b",
        dis=Disv(
            nlay=1,
            ncpl=1,
            nvert=4,
            top=1.0,
            botm=0.0,
            vertices=[(0, 0.0, 0.0), (1, 1.0, 0.0), (2, 1.0, 1.0), (3, 0.0, 1.0)],
            cell2d=[(0, 0.5, 0.5, 4, (0, 1, 2, 3))],
        ),
    )
    Gwfgwf(
        parent=sim,
        name="ab",
        exgmnamea="a",
        exgmnameb="b",
        exchangedata=[((0, 0, 1), (0, 0), 1, 0.5, 0.5, 1.0)],
        gnc=Gnc(gncdata=[((0, 0, 1), (0, 0), ((0, 1, 1),), (0.5,))]),
    )
    sim.write()

    exg = next(iter(Simulation.load(tmp_path / "mfsim.nam").exchanges))

    (row,) = exg.exchangedata
    assert (row.cellidm1, row.cellidm2) == ((0, 0, 1), (0, 0))
    assert (row.ihc, row.cl1, row.cl2, row.hwva) == (1, 0.5, 0.5, 1.0)
    assert exg.gnc is not None
    (gnc_row,) = exg.gnc.gncdata
    assert (gnc_row.cellidn, gnc_row.cellidm, gnc_row.cellidsj) == ((0, 0, 1), (0, 0), ((0, 1, 1),))
    assert gnc_row.alphasj == (0.5,)


@pytest.fixture()
def subdir_sim(tmp_path):
    """A simulation whose model lives in a subdirectory, as MF6 allows:
    every path in every file is relative to the simulation directory
    (``GWF6 gwf/m.nam``, ``DIS6 gwf/m.dis``, ``OPEN/CLOSE gwf/k.txt``)."""
    workspace = tmp_path / "sim"
    workspace.mkdir()
    sim = Simulation(name="sub", workspace=workspace, tdis=Time(perlen=[1.0], nstp=[1]))
    gwf = Gwf(
        parent=sim,
        name="m",
        filename="gwf/m.nam",
        dis=Dis(nlay=1, nrow=2, ncol=2, delr=1.0, delc=1.0, top=1.0, botm=0.0),
    )
    gwf.dis.filename = "gwf/m.dis"
    gwf.npf = Npf(k=1.0, filename="gwf/m.npf")
    sim.write()
    npf = workspace / "gwf" / "m.npf"
    npf.write_text(npf.read_text().replace("CONSTANT 1.0", "OPEN/CLOSE gwf/k.txt"))
    (workspace / "gwf" / "k.txt").write_text("1.0 2.0 3.0 4.0\n")
    return workspace


def test_load_model_in_subdirectory(subdir_sim, tmp_path, monkeypatch):
    """Paths resolve against the simulation directory, not the file naming
    them nor the cwd."""
    monkeypatch.chdir(tmp_path)

    gwf = Simulation.load(subdir_sim / "mfsim.nam")["m"]

    assert isinstance(gwf.dis, Dis)
    assert gwf.dis.get_dims()["nodes"] == 4
    np.testing.assert_array_equal(np.ravel(gwf.npf.k), [1.0, 2.0, 3.0, 4.0])
    assert gwf.filename.as_posix() == "gwf/m.nam"
    assert gwf.dis.filename.as_posix() == "gwf/m.dis"
    assert gwf.workspace == subdir_sim


def test_write_model_in_subdirectory(subdir_sim, tmp_path):
    """Writing a loaded simulation keeps its layout."""
    sim = Simulation.load(subdir_sim / "mfsim.nam")
    (tmp_path / "copy").mkdir()
    sim.workspace = tmp_path / "copy"
    sim.write()

    assert (tmp_path / "copy" / "gwf" / "m.nam").is_file()
    assert (tmp_path / "copy" / "gwf" / "m.dis").is_file()
    gwf = Simulation.load(tmp_path / "copy" / "mfsim.nam")["m"]
    assert gwf.filename.as_posix() == "gwf/m.nam"
    assert gwf.dis.filename.as_posix() == "gwf/m.dis"
    assert gwf.dis.get_dims()["nodes"] == 4


def test_load_model_alone_in_simulation(subdir_sim):
    """A model loads on its own given the simulation directory to resolve
    its paths against."""
    from flopy4.mf6 import LoadContext

    gwf = Gwf.load(subdir_sim / "gwf" / "m.nam", context=LoadContext(workspace=subdir_sim))

    assert gwf.dis.get_dims()["nodes"] == 4
    np.testing.assert_array_equal(np.ravel(gwf.npf.k), [1.0, 2.0, 3.0, 4.0])
    assert gwf.filename.as_posix() == "gwf/m.nam"


def test_model_workspace_follows_simulation(tmp_path):
    """A model's workspace is its simulation's, so moving the simulation
    moves its models' files."""
    sim = Simulation(name="sim", workspace=tmp_path / "a", tdis=Time(perlen=[1.0], nstp=[1]))
    gwf = Gwf(parent=sim, name="m", filename="gwf/m.nam", dis=Dis(nlay=1, nrow=1, ncol=1))
    gwf.dis.filename = "gwf/m.dis"

    sim.workspace = tmp_path / "b"

    assert gwf.workspace == tmp_path / "b"
    assert gwf.path == tmp_path / "b" / "gwf" / "m.nam"
    assert gwf.dis.path == tmp_path / "b" / "gwf" / "m.dis"


def test_model_workspace_under_simulation_is_not_settable(tmp_path):
    sim = Simulation(name="sim", workspace=tmp_path, tdis=Time(perlen=[1.0], nstp=[1]))
    gwf = Gwf(parent=sim, name="m", dis=Dis(nlay=1, nrow=1, ncol=1))

    gwf.workspace = tmp_path  # the simulation's: no change
    with pytest.raises(ValueError, match="simulation's workspace"):
        gwf.workspace = tmp_path / "gwf"


def test_standalone_model_keeps_own_workspace(tmp_path):
    gwf = Gwf(name="m", workspace=tmp_path, dis=Dis(nlay=1, nrow=1, ncol=1))
    gwf.workspace = tmp_path / "elsewhere"

    assert gwf.workspace == tmp_path / "elsewhere"
    assert gwf.dis.path == tmp_path / "elsewhere" / "m.dis"


def test_write_does_not_depend_on_cwd(tmp_path, monkeypatch):
    """Files are written to the workspace without changing into it."""
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")
    sim = Simulation(name="sim", workspace=tmp_path / "sim", tdis=Time(perlen=[1.0], nstp=[1]))
    gwf = Gwf(parent=sim, name="m", filename="gwf/m.nam", dis=Dis(nlay=1, nrow=1, ncol=1))
    gwf.dis.filename = "gwf/m.dis"

    sim.write()

    assert (tmp_path / "sim" / "gwf" / "m.dis").is_file()
    assert Path.cwd() == tmp_path / "elsewhere"
    assert not any((tmp_path / "elsewhere").iterdir())


def test_write_names_packages_attached_by_assignment(tmp_path):
    """A package swapped in by plain assignment (``gwf.chd = [...]``)
    after a write is named, and given its filename, from its model before
    the model's name file is written again."""
    sim = Simulation(name="sim", workspace=tmp_path, tdis=Time(perlen=[1.0], nstp=[1]))
    gwf = Gwf(parent=sim, name="m", dis=Dis(nlay=1, nrow=1, ncol=2))
    gwf.chd = [Chd(stress_period_data={0: [[(0, 0, 0), 1.0]]})]
    sim.write()

    del gwf.chd[0]
    gwf.chd = [Chd(stress_period_data={0: [[(0, 0, 0), 2.0]]})]
    sim.write()

    assert " CHD6 m.chd chd0" in (tmp_path / "m.nam").read_text().splitlines()
    assert (tmp_path / "m.chd").is_file()


def test_loads_a_new_model_type(tmp_path):
    """A `Chf` model (a 1D channel network, `Disv1d`-discretized) writes
    and loads like any other model type -- guards `flopy4.mf6.__init__`'s
    `_COMPONENT_MODULES` registration, without which `Simulation.load()`
    silently drops the model (warns "no field takes models entry CHF6")."""
    from flopy4.mf6.chf import Chf
    from flopy4.mf6.chf.dfw import Dfw
    from flopy4.mf6.chf.disv1d import Disv1d
    from flopy4.mf6.chf.ic import Ic as ChfIc

    sim = Simulation(name="sim", workspace=tmp_path, tdis=Time(perlen=[1.0], nstp=[1]))
    chf = Chf(parent=sim, name="m")
    Disv1d(
        parent=chf,
        nodes=2,
        nvert=3,
        vertices=[(0, 0.0, 0.0), (1, 10.0, 0.0), (2, 20.0, 0.0)],
        cell1d=[(0, 0.5, 2, (0, 1)), (1, 0.5, 2, (1, 2))],
        bottom=[0.0, 0.0],
        idomain=[1, 1],
    )
    ChfIc(parent=chf, strt=[1.0, 1.0])
    Dfw(parent=chf, manningsn=[0.035, 0.035])
    sim.write()

    loaded = Simulation.load(tmp_path / "mfsim.nam")

    assert [type(m).__name__ for m in loaded.models] == ["Chf"]
    assert loaded.models[0].name == "m"
    assert loaded.models[0].disv1d.nodes == 2


def test_loads_a_new_olf_model_type(tmp_path):
    """An `Olf` model (an overland-flow model, `Dis2d`-discretized) writes
    and loads like any other model type -- guards `flopy4.mf6.__init__`'s
    `_COMPONENT_MODULES` registration, without which `Simulation.load()`
    silently drops the model (warns "no field takes models entry OLF6")."""
    from flopy4.mf6.olf import Olf
    from flopy4.mf6.olf.dfw import Dfw
    from flopy4.mf6.olf.dis2d import Dis2d
    from flopy4.mf6.olf.ic import Ic as OlfIc

    sim = Simulation(name="sim", workspace=tmp_path, tdis=Time(perlen=[1.0], nstp=[1]))
    olf = Olf(parent=sim, name="m")
    Dis2d(parent=olf, nrow=1, ncol=2, delr=1.0, delc=1.0, bottom=0.0)
    OlfIc(parent=olf, strt=[1.0, 1.0])
    Dfw(parent=olf, manningsn=[0.035, 0.035])
    sim.write()

    loaded = Simulation.load(tmp_path / "mfsim.nam")

    assert [type(m).__name__ for m in loaded.models] == ["Olf"]
    assert loaded.models[0].name == "m"
    assert (loaded.models[0].dis2d.nrow, loaded.models[0].dis2d.ncol) == (1, 2)


def test_exchange_resolves_cellid_widths_per_model(tmp_path):
    """A `Chfgwf` exchange's `EXCHANGEDATA` row gives each side's cellid
    its own model's width (1 for `Chf`'s `disv1d`, 3 for `Gwf`'s `dis`) --
    guards `LoadContext._exchange_widths()`'s generic `resolve_dims()`
    lookup, which replaced a hardcoded `.dis` attribute check that only
    worked for `Gwf`-shaped models."""
    from flopy4.mf6.chf import Chf
    from flopy4.mf6.chf.dfw import Dfw
    from flopy4.mf6.chf.disv1d import Disv1d
    from flopy4.mf6.chf.ic import Ic as ChfIc
    from flopy4.mf6.exg.chfgwf import Chfgwf

    sim = Simulation(name="sim", workspace=tmp_path, tdis=Time(perlen=[1.0], nstp=[1]))
    chf = Chf(parent=sim, name="chfmodel")
    Disv1d(
        parent=chf,
        nodes=2,
        nvert=3,
        vertices=[(0, 0.0, 0.0), (1, 10.0, 0.0), (2, 20.0, 0.0)],
        cell1d=[(0, 0.5, 2, (0, 1)), (1, 0.5, 2, (1, 2))],
        bottom=[0.0, 0.0],
        idomain=[1, 1],
    )
    ChfIc(parent=chf, strt=[1.0, 1.0])
    Dfw(parent=chf, manningsn=[0.035, 0.035])

    gwf = Gwf(parent=sim, name="gwfmodel", dis=Dis(nlay=1, nrow=1, ncol=2))
    Ic(parent=gwf, strt=1.0)
    Npf(parent=gwf, icelltype=0, k=1.0)

    Chfgwf(
        parent=sim,
        exgmnamea="chfmodel",
        exgmnameb="gwfmodel",
        nexg=2,
        exchangedata=[
            Chfgwf.Exchangedata(cellidm1=(0,), cellidm2=(0, 0, 0), bedleak=1.0, cfact=1.0),
            Chfgwf.Exchangedata(cellidm1=(1,), cellidm2=(0, 0, 1), bedleak=1.0, cfact=1.0),
        ],
    )
    sim.write()

    loaded = Simulation.load(tmp_path / "mfsim.nam")
    rows = loaded.exchanges[0].exchangedata

    assert [(r.cellidm1, r.cellidm2) for r in rows] == [
        ((0,), (0, 0, 0)),
        ((1,), (0, 0, 1)),
    ]


def test_exchange_resolves_cellid_widths_for_dis2d(tmp_path):
    """An `Olfgwf` exchange's `EXCHANGEDATA` row gives each side's cellid
    its own model's width (2 for `Olf`'s `dis2d`, a layerless structured
    grid, 3 for `Gwf`'s `dis`) -- guards `ncelldim_from_dims()`, which
    used to assume any `nrow`/`ncol` pair implied a 3-wide, layered
    cellid; `Dis2d` has `nrow`/`ncol` but no `nlay` at all."""
    from flopy4.mf6.exg.olfgwf import Olfgwf
    from flopy4.mf6.olf import Olf
    from flopy4.mf6.olf.dfw import Dfw
    from flopy4.mf6.olf.dis2d import Dis2d
    from flopy4.mf6.olf.ic import Ic as OlfIc

    sim = Simulation(name="sim", workspace=tmp_path, tdis=Time(perlen=[1.0], nstp=[1]))
    olf = Olf(parent=sim, name="olfmodel")
    Dis2d(parent=olf, nrow=1, ncol=2, delr=1.0, delc=1.0, bottom=0.0)
    OlfIc(parent=olf, strt=[1.0, 1.0])
    Dfw(parent=olf, manningsn=[0.035, 0.035])

    gwf = Gwf(parent=sim, name="gwfmodel", dis=Dis(nlay=1, nrow=1, ncol=2))
    Ic(parent=gwf, strt=1.0)
    Npf(parent=gwf, icelltype=0, k=1.0)

    Olfgwf(
        parent=sim,
        exgmnamea="olfmodel",
        exgmnameb="gwfmodel",
        nexg=2,
        exchangedata=[
            Olfgwf.Exchangedata(cellidm1=(0, 0), cellidm2=(0, 0, 0), bedleak=1.0, cfact=1.0),
            Olfgwf.Exchangedata(cellidm1=(0, 1), cellidm2=(0, 0, 1), bedleak=1.0, cfact=1.0),
        ],
    )
    sim.write()

    loaded = Simulation.load(tmp_path / "mfsim.nam")
    rows = loaded.exchanges[0].exchangedata

    assert [(r.cellidm1, r.cellidm2) for r in rows] == [
        ((0, 0), (0, 0, 0)),
        ((0, 1), (0, 0, 1)),
    ]


def test_loads_cdb_stress_period_data(tmp_path):
    """`Cdb` (CHF's channel-divergence boundary package) round-trips its
    stress period data -- the one CHF package type no upstream test
    exercises at all, so it's otherwise entirely unverified."""
    from flopy4.mf6.chf import Chf
    from flopy4.mf6.chf.cdb import Cdb
    from flopy4.mf6.chf.dfw import Dfw
    from flopy4.mf6.chf.disv1d import Disv1d
    from flopy4.mf6.chf.ic import Ic as ChfIc

    sim = Simulation(name="sim", workspace=tmp_path, tdis=Time(perlen=[1.0], nstp=[1]))
    chf = Chf(parent=sim, name="m")
    Disv1d(
        parent=chf,
        nodes=2,
        nvert=3,
        vertices=[(0, 0.0, 0.0), (1, 10.0, 0.0), (2, 20.0, 0.0)],
        cell1d=[(0, 0.5, 2, (0, 1)), (1, 0.5, 2, (1, 2))],
        bottom=[0.0, 0.0],
        idomain=[1, 1],
    )
    ChfIc(parent=chf, strt=[1.0, 1.0])
    Dfw(parent=chf, manningsn=[0.035, 0.035])
    Cdb(parent=chf, stress_period_data={0: [[(0,), 0, 1.0]]})
    sim.write()

    loaded = Simulation.load(tmp_path / "mfsim.nam")
    (row,) = loaded.models[0].cdb[0].stress_period_data[0]

    assert (row.cellid, row.idcxs, row.width) == ((0,), 0, 1.0)


def test_loads_olf_cdb_stress_period_data(tmp_path):
    """`Cdb` (OLF's channel-divergence boundary package) round-trips its
    stress period data -- the one OLF package type no upstream test
    exercises at all, so it's otherwise entirely unverified."""
    from flopy4.mf6.olf import Olf
    from flopy4.mf6.olf.cdb import Cdb
    from flopy4.mf6.olf.dfw import Dfw
    from flopy4.mf6.olf.dis2d import Dis2d
    from flopy4.mf6.olf.ic import Ic as OlfIc

    sim = Simulation(name="sim", workspace=tmp_path, tdis=Time(perlen=[1.0], nstp=[1]))
    olf = Olf(parent=sim, name="m")
    Dis2d(parent=olf, nrow=1, ncol=2, delr=1.0, delc=1.0, bottom=0.0)
    OlfIc(parent=olf, strt=[1.0, 1.0])
    Dfw(parent=olf, manningsn=[0.035, 0.035])
    Cdb(parent=olf, stress_period_data={0: [[(0, 0), 0, 1.0]]})
    sim.write()

    loaded = Simulation.load(tmp_path / "mfsim.nam")
    (row,) = loaded.models[0].cdb[0].stress_period_data[0]

    assert (row.cellid, row.idcxs, row.width) == ((0, 0), 0, 1.0)


def test_loads_evp_stress_period_data(tmp_path):
    """`Evp` (CHF's evaporation package) round-trips its stress period
    data -- the other CHF package type no upstream test exercises at
    all (alongside `Cdb`), so it's otherwise entirely unverified."""
    from flopy4.mf6.chf import Chf
    from flopy4.mf6.chf.dfw import Dfw
    from flopy4.mf6.chf.disv1d import Disv1d
    from flopy4.mf6.chf.evp import Evp
    from flopy4.mf6.chf.ic import Ic as ChfIc

    sim = Simulation(name="sim", workspace=tmp_path, tdis=Time(perlen=[1.0], nstp=[1]))
    chf = Chf(parent=sim, name="m")
    Disv1d(
        parent=chf,
        nodes=2,
        nvert=3,
        vertices=[(0, 0.0, 0.0), (1, 10.0, 0.0), (2, 20.0, 0.0)],
        cell1d=[(0, 0.5, 2, (0, 1)), (1, 0.5, 2, (1, 2))],
        bottom=[0.0, 0.0],
        idomain=[1, 1],
    )
    ChfIc(parent=chf, strt=[1.0, 1.0])
    Dfw(parent=chf, manningsn=[0.035, 0.035])
    Evp(parent=chf, stress_period_data={0: [[(0,), 0.01]]})
    sim.write()

    loaded = Simulation.load(tmp_path / "mfsim.nam")
    (row,) = loaded.models[0].evp[0].stress_period_data[0]

    assert (row.cellid, row.evaporation) == ((0,), 0.01)


def test_loads_olf_evp_stress_period_data(tmp_path):
    """`Evp` (OLF's evaporation package) round-trips its stress period
    data -- the other OLF package type no upstream test exercises at
    all (alongside `Cdb`), so it's otherwise entirely unverified."""
    from flopy4.mf6.olf import Olf
    from flopy4.mf6.olf.dfw import Dfw
    from flopy4.mf6.olf.dis2d import Dis2d
    from flopy4.mf6.olf.evp import Evp
    from flopy4.mf6.olf.ic import Ic as OlfIc

    sim = Simulation(name="sim", workspace=tmp_path, tdis=Time(perlen=[1.0], nstp=[1]))
    olf = Olf(parent=sim, name="m")
    Dis2d(parent=olf, nrow=1, ncol=2, delr=1.0, delc=1.0, bottom=0.0)
    OlfIc(parent=olf, strt=[1.0, 1.0])
    Dfw(parent=olf, manningsn=[0.035, 0.035])
    Evp(parent=olf, stress_period_data={0: [[(0, 0), 0.01]]})
    sim.write()

    loaded = Simulation.load(tmp_path / "mfsim.nam")
    (row,) = loaded.models[0].evp[0].stress_period_data[0]

    assert (row.cellid, row.evaporation) == ((0, 0), 0.01)
