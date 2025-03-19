import numpy as np

from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.tdis import Tdis

# TODO rewrite bottom up

ws = "./mymodel"
name = "mymodel"
tdis = Tdis()
sim = Simulation(name=name, tdis=tdis)
dis = Dis(nrow=10, ncol=10)
gwf = Gwf(parent=sim, name=name, save_flows=True, dis=dis)
ic = Ic(parent=gwf)
npf = Npf(parent=gwf, save_specific_discharge=True)
chd = Chd(
    parent=gwf,
    head={"*": {(0, 0, 0): 1.0, (0, 9, 9): 0.0}},
)

# adopt xarray paradigm. transpose lists to arrays. this
# is no longer "sparse": in the sense that lists specify
# <maxbound> features of interest, where arrays specify
# the entire domain. but to maximize the value of xarray
# we want to "align" everything to the discretization in
# both time and space.

assert chd.data["head"][0, 0] == 1.0
assert chd.data["head"][0, 99] == 0.0
assert np.allclose(chd.data["head"][:, 1:99], np.full(98, 1e30))

# TODO: xarray index aliasing nlay/ncol/nrow to k/i/j?
# assert chd.data["head"].loc(dict(k=0, i=0, j=0)) == 1.
# assert chd.data["head"].loc(dict(k=0, i=9, j=9)) == 0.

# TODO OC!

# oc = Oc(
#     gwf,
#     budget_filerecord=f"{name}.bud",
#     head_filerecord=f"{name}.hds",
#     saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")],
# )

# xarray style. this is how imod-python does it too.
# assert oc.data["save_head"] == "all"
# assert oc.data["save_budget"] == "all"
