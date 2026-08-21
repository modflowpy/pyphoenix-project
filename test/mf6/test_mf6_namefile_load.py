"""Tests for recursive namefile loading (Simulation.load()/Gwf.load()).

Builds a small Gwf model via the existing, working Python construction API
(mirroring docs/examples/quickstart.py), writes it with the existing,
working egress path, then loads it back and checks the tree was resolved
correctly: dis attached (with the right model-scoped class), dims threaded
into npf's griddata shapes, chd's list-input round-tripped, and ims
attached under the simulation's solutions.
"""

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
        save_head={0: "all"},
        save_budget={0: "all"},
    )
    sim.write()
    return workspace


def test_load_simulation_resolves_model_and_solution(written_sim):
    loaded = Simulation.load(written_sim / "mfsim.nam")

    assert len(loaded.models) == 1
    gwf = next(iter(loaded.models.values()))
    assert isinstance(gwf, Gwf)

    assert len(loaded.solutions) == 1
    ims = next(iter(loaded.solutions.values()))
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
    """A dict-kind binding field (Simulation.models/exchanges/solutions)
    round-trips a custom pname -- xattree reconciles a dict child's name
    to the key it's attached under, so the namefile row's pname (not the
    referenced file's name, which the row's pname needn't match) has to
    become that key. Scalar/list package fields (dis, chd, ...) can't
    round-trip a custom pname the same way: xattree reconciles those to a
    field-derived name regardless of what's passed, confirmed true even
    for the original write (not something this fix could or should
    change -- it's xattree's own child-attachment convention)."""
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
