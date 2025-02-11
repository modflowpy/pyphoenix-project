"""
We reproduce the FloPy README example.

We ask the question how, in general, to
provide transient data to components.

In particular we consider CHD and OC.

Transient (i.e. stress period) data are
the worst-case limit of the data model
re: nesting depth and composite types.
Everything else is easier to represent.

An important consideration is to what
degree FloPy should comport with the
existing MF6 specification and type
system defined in it, where it can
"interpret" the spec in a way more
natural for Python, and where it may
instead be better to update the spec.

We explore a few options, some which
map directly to the spec as it exists,
some which take some liberties with it,
and some which would probably need DFN
changes to support.
"""

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

# CHD. first, nothing but builtins.
chd = Chd(
    gwf,
    # 1) tuples (like flopy3)
    stress_period_data=[[(0, 0, 0), 1.0], [(0, 9, 9), 0.0]],
    #
    # (a tangential idea)
    # "*" could mean "apply to all stress periods"?
    # this is the default anyway if only one period
    # is specified. "*" is just a bit more explicit
    # stress_period_data={
    #     "*": [[(0, 0, 0), 1.], [(0, 9, 9), 0.]]
    # }
    #
    # 2) dictionaries
    # stress_period_data=[
    #     {(0, 0, 0): {"head": 1.}, (0, 9, 9): {"head": 0.}}
    # ]
    #
    # 3) typed records
    # stress_period_data=[
    #     Chd.Period(cellid=(0, 0, 0), head=1.),
    #     Chd.Period(cellid=(0, 9, 9), head=0.),
    # ],
)

# alternatively, CHD with duck arrays.
#
# 4) xarray, scalar dtypes
# chd.data["head"].loc(dict(k=0, i=0, j=0)) = 1.
# chd.data["head"].loc(dict(k=0, i=9, j=9)) = 0.
#
# 5) xarray, object dtype
# chd.data["stress_period_data"].loc(dict(k=0, i=0, j=0)) = Chd.Period(head=1.)
# chd.data["stress_period_data"].loc(dict(k=0, i=9, j=9)) = Chd.Period(head=0.)
#
# 5a) xarray, object dtype, labeled vars (does this work? TODO test it)
# chd.data["stress_period_data"].loc(dict(k=0, i=0, j=0, var="head")) = 1.
# chd.data["stress_period_data"].loc(dict(k=0, i=9, j=9, var="head")) = 0.
# TODO does this work?
# chd.data["stress_period_data"].loc(dict(k=0, i=0, j=0)) = (1., 0.)
# chd.data["stress_period_data"].loc(dict(k=0, i=9, j=9)) = (0., 0.)

#
# 6) sparse array
# spd = sparse.COO([[0,0], [0,9], [0,9]], [1., 0.])
# chd = Chd(gwf, stress_period_data=spd)

# OC. first with builtins
budget_file = name + ".bud"
head_file = name + ".hds"
oc = Oc(
    gwf,
    budget_filerecord=budget_file,
    head_filerecord=head_file,
    # 1) tuples (like flopy3)
    perioddata=[("HEAD", "ALL"), ("BUDGET", "ALL")],
    # 2) typed records
    # save=[
    #     Oc.Period(rtype="head", steps="all"),
    #     Oc.Period(rtype="budget", steps="all"),
    # ],
    # 3a) dicts, {period: {var: steps}}
    # save={"*": {"head": "all", "budget": "all"}},
    # 3b) dicts, {var: {period: steps}}
    # save={"head": {"*": "all"}, "budget": {"*": "all"}},
)

# OC with duck arrays.
#
# 4) xarray, scalar dtypes. this is how imod-python does it:
# https://deltares.github.io/imod-python/api/generated/mf6/imod.mf6.OutputControl.html
# oc.data["save_head"] = "all"
# oc.data["save_budget"] = "all"
# limitation: no support for 'steps a b c ...' syntax due to ragged nature.
#
# 5) xarray, object dtypes
# oc.data["save_head"] = Oc.Steps_("all")
# oc.data["save_budget"] = Oc.Steps_("all")
# this supports arbitrary step selections
# oc.data["save_budget"] = Oc.Steps_("steps", 1)

# TODO? mock some output
# sim.write_simulation()
# sim.run_simulation()


# TODO? try to reproduce plots with xarray
# head = gwf.output.head().get_data()
# bud = gwf.output.budget()
# spdis = bud.get_data(text='DATA-SPDIS')[0]
# qx, qy, qz = flopy.utils.postprocessing.get_specific_discharge(spdis, gwf)
# pmv = flopy.plot.PlotMapView(gwf)
# pmv.plot_array(head)
# pmv.plot_grid(colors='white')
# pmv.contour_array(head, levels=[.2, .4, .6, .8], linewidths=3.)
# pmv.plot_vector(qx, qy, normalize=True, color="white")
