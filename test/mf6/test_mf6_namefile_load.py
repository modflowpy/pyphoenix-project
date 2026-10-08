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
    gwf = next(iter(loaded.models.values()))
    assert isinstance(gwf, Gwf)

    assert len(loaded.solutiongroup) == 1
    ims = next(iter(loaded.solutiongroup.values()))
    assert isinstance(ims, Ims)
    assert ims.models == ["mymodel"]


def test_load_simulation_resolves_dis_and_dims(written_sim):
    gwf = next(iter(Simulation.load(written_sim / "mfsim.nam").models.values()))

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
    gwf = next(iter(Simulation.load(written_sim / "mfsim.nam").models.values()))

    assert isinstance(gwf.npf, Npf)
    assert gwf.npf.k.shape == (100,)
    assert np.all(gwf.npf.k == 1.0)

    assert isinstance(gwf.ic, Ic)
    assert gwf.ic.strt.shape == (100,)
    assert np.all(gwf.ic.strt == 1.0)


def test_load_simulation_resolves_list_package_rows(written_sim):
    gwf = next(iter(Simulation.load(written_sim / "mfsim.nam").models.values()))

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
    """A dict-kind binding field (Simulation.models/exchanges/solutiongroup)
    round-trips a custom pname via the child's own `.name` -- child
    attachment reconciles a dict child's name to the key it's attached
    under, so the namefile row's pname (not the referenced file's name,
    which the row's pname needn't match) has to become that key. See
    `test_load_preserves_list_package_pname` below for the equivalent
    round trip on a list-kind package field."""
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

    assert list(loaded.models.keys()) == ["a_custom_model_name"]
    gwf = loaded.models["a_custom_model_name"]
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

    gwf = next(iter(Simulation.load(written_sim / "mfsim.nam").models.values()))
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

    exg = next(iter(Simulation.load(tmp_path / "mfsim.nam").exchanges.values()))

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

    gwf = Simulation.load(subdir_sim / "mfsim.nam").models["m"]

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
    gwf = Simulation.load(tmp_path / "copy" / "mfsim.nam").models["m"]
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
