from pathlib import Path

import flopy
from lark import Lark

from flopy4.mf6 import Tdis
from flopy4.mf6.io import MF6Transformer, make_parser


def test_make_parser():
    parser = make_parser(Tdis)
    assert isinstance(parser, Lark)


def readme_example(name: str, workspace: Path) -> flopy.mf6.MFSimulation:
    sim = flopy.mf6.MFSimulation(
        sim_name=name, sim_ws=workspace, exe_name="mf6"
    )
    tdis = flopy.mf6.ModflowTdis(sim)
    ims = flopy.mf6.ModflowIms(sim)
    gwf = flopy.mf6.ModflowGwf(sim, modelname=name, save_flows=True)
    dis = flopy.mf6.ModflowGwfdis(gwf, nrow=10, ncol=10)
    ic = flopy.mf6.ModflowGwfic(gwf)
    npf = flopy.mf6.ModflowGwfnpf(gwf, save_specific_discharge=True)
    chd = flopy.mf6.ModflowGwfchd(
        gwf, stress_period_data=[[(0, 0, 0), 1.0], [(0, 9, 9), 0.0]]
    )
    budget_file = name + ".bud"
    head_file = name + ".hds"
    oc = flopy.mf6.ModflowGwfoc(
        gwf,
        budget_filerecord=budget_file,
        head_filerecord=head_file,
        saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")],
    )
    return sim


def test_parse(tmp_path):
    sim = readme_example("test", Path(tmp_path))
    sim.write_simulation()
    parser = make_parser(Tdis)
    transformer = MF6Transformer()
    with open(tmp_path / "test.tdis", "r") as f:
        tree = parser.parse(f.read())
        data = transformer.transform(tree)
