from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from flopy.discretization.modeltime import ModelTime
from flopy.discretization.structuredgrid import StructuredGrid

from flopy4.mf6.gwf import Chd, Gwf, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation

name = "quickstart"
workspace = Path(__file__).parent / name
time = ModelTime(perlen=[1.0], nstp=[1])
grid = StructuredGrid(nlay=1, nrow=10, ncol=10)
sim = Simulation(name=name, workspace=workspace, tdis=time)
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

# sim.write()
sim.run(verbose=True)

# check CHD
assert chd.data["head"][0, 0] == 1.0
assert chd.data.head.sel(per=0)[99] == 0.0
assert np.allclose(chd.data.head[:, 1:99], np.full(98, 1e30))

# check DIS
assert gwf.dis.data.botm.sel(lay=0, col=0, row=0) == 0.0

# check OC
assert oc.data["save_head"][0] == "all"
assert oc.data.save_head.sel(per=0) == "all"

# get head and budget results
budget = gwf.output.budget.squeeze()
head = gwf.output.head.squeeze()

# make plot
fig, ax = plt.subplots()
ax.tick_params()
ax.set_xticks(np.arange(0, 11, 2), minor=False)
ax.set_xticks(np.arange(1, 10, 2), minor=True)
ax.set_yticks(np.arange(0, 11, 2), minor=False)
ax.set_yticks(np.arange(1, 10, 2), minor=True)
ax.grid(which="both", color="white")
head.plot.imshow(ax=ax)
head.plot.contour(ax=ax, levels=[0.2, 0.4, 0.6, 0.8], linewidths=3.0)
budget.plot.quiver(x="x", y="y", u="npf-qx", v="npf-qy", ax=ax, color="white")
fig.savefig(workspace / ".." / "image" / "quickstart.png")
