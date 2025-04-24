import numpy as np

from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.tdis import Tdis

ws = "./mymodel"
name = "mymodel"
tdis = Tdis()
ims = Ims()
sim = Simulation(name=name, tdis=tdis, solutions={"ims": ims})
dis = Dis(nrow=10, ncol=10)
gwf = Gwf(parent=sim, name=name, save_flows=True, dis=dis)
ic = Ic(parent=gwf)
npf = Npf(parent=gwf, save_specific_discharge=True)
chd = Chd(
    parent=gwf,
    head={"*": {(0, 0, 0): 1.0, (0, 9, 9): 0.0}},
)
oc = Oc(
    parent=gwf,
    budget_file=f"{name}.bud",
    head_file=f"{name}.hds",
    save_head={"*": "all"},
    save_budget={"*": "all"},
)

# check CHD
assert chd.data["head"][0, 0].item() == 1.0
assert chd.data["head"][0, 99].item() == 0.0
assert np.allclose(chd.data["head"][:, 1:99].data.todense(), np.full(98, 1e30))

# TODO: xarray index aliasing nlay/ncol/nrow to k/i/j?
# assert chd.data["head"].loc(dict(k=0, i=0, j=0)) == 1.
# assert chd.data["head"].loc(dict(k=0, i=9, j=9)) == 0.

# check OC
assert oc.data["save_head"][0].item() == "all"
assert oc.data["save_budget"][0].item() == "all"
