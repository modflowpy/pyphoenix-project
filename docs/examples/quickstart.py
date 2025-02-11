from flopy4.mf6 import Sim, Tdis
from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc

ws = "./mymodel"
name = "mymodel"
sim = Sim(name=name, path=ws, exe="mf6")
tdis = Tdis(sim)
gwf = Gwf(sim, name=name, save_flows=True)
dis = Dis(gwf, nrow=10, ncol=10)
ic = Ic(gwf)
npf = Npf(gwf, save_specific_discharge=True)
chd = Chd(
    gwf,
    stress_period_data=[[(0, 0, 0), 1.0], [(0, 9, 9), 0.0]],
)

# list input in the mf6 paradigm, just stored in xarray.
# this is straightforward to implement. even in flopy3?
assert all(
    period == Chd.StressPeriodData((0, 0, 0), 1.0)
    for period in chd.data["stress_period_data"]
)

# adopt xarray paradigm. transpose lists to arrays. this
# is no longer "sparse": in the sense that lists specify
# <maxbound> features of interest, where arrays specify
# the entire domain. but to maximize the value of xarray
# we want to "align" everything to the discretization in
# both time and space.

# assert chd.data["head"].loc(dict(k=0, i=0, j=0)) == 1.
# assert chd.data["head"].loc(dict(k=0, i=9, j=9)) == 0.

oc = Oc(
    gwf,
    budget_filerecord=f"{name}.bud",
    head_filerecord=f"{name}.hds",
    saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")],
)

# xarray style. this is how imod-python does it too.
# assert oc.data["save_head"] == "all"
# assert oc.data["save_budget"] == "all"
