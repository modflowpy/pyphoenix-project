from pathlib import Path

import flopy
import matplotlib.pyplot as plt
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
assert chd.data["head"][0, 0] == 1.0
assert chd.data.head.sel(per=0)[99] == 0.0
assert np.allclose(chd.data.head[:, 1:99], np.full(98, 1e30))

# check DIS
assert dis.data.botm.sel(lay=0, col=0, row=0) == 0.0

# check OC
assert oc.data["save_head"][0] == "all"
assert oc.data.save_head.sel(per=0) == "all"

# PLOT
# create budget reader
bpth = Path("./quickstart_data/mymodel.bud")
bobj = flopy.utils.CellBudgetFile(bpth, precision="double")

# set specific discharge
spdis = bobj.get_data(text="DATA-SPDIS")[0]

# create head reader
hpth = Path("./quickstart_data/mymodel.hds")
hobj = flopy.utils.HeadFile(hpth, precision="double")

# set heads
heads = hobj.get_alldata()

# create grid
grbpth = Path("./quickstart_data/mymodel.dis.grb")
grid = flopy.discretization.StructuredGrid.from_binary_grid_file(grbpth)

# TODO: get_specific_discharge is dependent on flopy3 model
# qx, qy, qz = flopy.utils.postprocessing.get_specific_discharge(spdis, gwf)

# set discharge component arrays
u = []
v = []
for r in spdis:
    u.append(r[3])
    v.append(r[4])
qx = np.array(u).reshape(grid.nrow, grid.ncol)
qy = np.array(v).reshape(grid.nrow, grid.ncol)

fig, ax = plt.subplots()
pmv = flopy.plot.PlotMapView(modelgrid=grid, ax=ax)
pmv.plot_array(heads[0][0])
pmv.plot_grid(colors="white")
pmv.contour_array(heads[0][0], levels=[0.2, 0.4, 0.6, 0.8], linewidths=3.0)
pmv.plot_vector(qx, qy, normalize=True, color="white")
qs_pth = Path("./image/quickstart.png")
fig.savefig(qs_pth)
