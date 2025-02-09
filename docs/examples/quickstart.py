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
    stress_period_data=[
        # TODO? accept raw tuples for
        # parity with flopy3 example?
        Chd.StressPeriodData(cellid=(0, 0, 0), head=1.0),
        Chd.StressPeriodData(cellid=(0, 9, 9), head=1.0),
    ],
)

# TODO? xarray alternative
# chd.data["stress_period_data"].loc(dict(i=0, j=0, k=0)) = 1.
# chd.data["stress_period_data"].loc(dict(i=0, j=9, k=9)) = 0.

# TODO? sparse array alternative
# spd = sparse.COO([[0,0], [0,9], [0,9]], [1., 0.])
# chd = flopy4.mf6.ModflowGwfchd(gwf, stress_period_data=spd)

budget_file = name + ".bud"
head_file = name + ".hds"
oc = Oc(
    gwf,
    budget_filerecord=budget_file,
    head_filerecord=head_file,
    perioddata=[("HEAD", "ALL"), ("BUDGET", "ALL")],
    # TODO: format we want to support
    # save={"head": {0: "ALL"}, "budget": {0: "ALL"}},
    # print={"budget": {0: np.ones((tdis.nstp[0]))}, "budget": {0, "ALL"}},
)

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
