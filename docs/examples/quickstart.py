from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.tdis import Tdis

ws = "./quickstart_data"
name = "mymodel"
tdis = Tdis()
ims = Ims()
sim = Simulation(name=name, tdis=tdis, solutions={"ims": ims}, sim_ws=ws)
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

# set specific discharge
spdis = gwf.output.budget
heads = gwf.output.head
sq = heads.squeeze()

fig, ax = plt.subplots()
ax.tick_params()
ax.set_xticks(np.arange(0, 11, 2), minor=False)
ax.set_xticks(np.arange(1, 10, 2), minor=True)
ax.set_yticks(np.arange(0, 11, 2), minor=False)
ax.set_yticks(np.arange(1, 10, 2), minor=True)
ax.grid(which="both", color="white")
sq.plot.imshow(ax=ax)
sq.plot.contour(ax=ax, levels=[0.2, 0.4, 0.6, 0.8], linewidths=3.0)
spdis.squeeze().plot.quiver(
    x="x", y="y", u="npf-qx", v="npf-qy", ax=ax, color="white"
)
qs_pth = Path("./image/quickstart.png")
fig.savefig(qs_pth)
