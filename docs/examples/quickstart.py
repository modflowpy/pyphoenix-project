from pathlib import Path

import flopy
import imod.mf6
import matplotlib.pyplot as plt
import numpy as np

from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.interface.flopy3 import Flopy3Model
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

# flopy3 model interface
gwf3 = Flopy3Model(gwf)

# check CHD
assert chd.data["head"][0, 0] == 1.0
assert chd.data.head.sel(per=0)[99] == 0.0
assert np.allclose(chd.data.head[:, 1:99], np.full(98, 1e30))

# check DIS
assert dis.data.botm.sel(lay=0, col=0, row=0) == 0.0

# check OC
assert oc.data["save_head"][0] == "all"
assert oc.data.save_head.sel(per=0) == "all"

# set paths
bpth = Path("./quickstart_data/mymodel.bud")
grbpth = Path("./quickstart_data/mymodel.dis.grb")
hpth = Path("./quickstart_data/mymodel.hds")

# set data
bobj = flopy.utils.CellBudgetFile(bpth, precision="double")
spdis = bobj.get_data(text="DATA-SPDIS")[0]
# spdis = imod.mf6.open_cbc(bpth, grbpth, merge_to_dataset=True)
heads = imod.mf6.open_hds(hpth, grbpth)

# discharge vectors
qx, qy, qz = flopy.utils.postprocessing.get_specific_discharge(spdis, gwf3)

# plot
fig, ax = plt.subplots()
pmv = flopy.plot.PlotMapView(model=gwf3, ax=ax)
pmv.plot_array(heads[0][0])
pmv.plot_grid(colors="white")
pmv.contour_array(heads[0][0], levels=[0.2, 0.4, 0.6, 0.8], linewidths=3.0)
pmv.plot_vector(qx, qy, color="white")
qs_pth = Path("./image/quickstart.png")
fig.savefig(qs_pth)
