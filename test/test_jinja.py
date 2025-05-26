from pathlib import Path

from flopy.discretization import StructuredGrid
from flopy.discretization.modeltime import ModelTime
from jinja2 import Environment, PackageLoader

from flopy4.mf6 import filters
from flopy4.mf6.gwf import Chd, Gwf, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.spec import blocks_dict, fields_dict


def test_simulation_to_jinja():
    name = "quickstart"
    workspace = Path(__file__).parent / name
    time = ModelTime(perlen=[1.0], nstp=[1])
    grid = StructuredGrid(nlay=1, nrow=10, ncol=10)
    sim = Simulation(name=name, path=workspace, tdis=time)
    ims = Ims(parent=sim)
    gwf_name = "mymodel"
    gwf = Gwf(parent=sim, name=gwf_name, save_flows=True, dis=grid)
    npf = Npf(parent=gwf, save_specific_discharge=True)
    chd = Chd(
        parent=gwf,
        head={"*": {(0, 0, 0): 1.0, (0, 9, 9): 0.0}},
    )
    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf.name}.bud",
        head_file=f"{gwf.name}.hds",
        save_head={"*": "all"},
        save_budget={"*": "all"},
    )

    env = Environment(
        loader=PackageLoader("flopy4.mf6"),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["fieldkind"] = filters.fieldkind
    env.filters["fieldvalue"] = filters.fieldvalue
    env.filters["arraydelayed"] = filters.arraydelayed
    env.filters["array2string"] = filters.array2string

    fields = fields_dict(Oc)
    blocks = blocks_dict(Oc)
    result = env.get_template("blocks.jinja").render(fields=fields, blocks=blocks, data=oc.data)
    assert result != ""
