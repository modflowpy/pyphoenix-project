from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from flopy.discretization.modeltime import ModelTime
from flopy.discretization.structuredgrid import StructuredGrid

from flopy4.mf6.modflow.gwf import Chd, Gwf, Ic, Npf, Oc
from flopy4.mf6.modflow.sim import Simulation
from flopy4.mf6.modflow.slnims import Ims

name = "quickstart"
workspace = Path(__file__).parent / name
time = ModelTime(perlen=[1.0], nstp=[1])
grid = StructuredGrid(
    nlay=1,
    nrow=10,
    ncol=10,
    delr=1.0 * np.ones(10),
    delc=1.0 * np.ones(10),
    top=1.0 * np.ones((10, 10)),
    botm=0.0 * np.ones((1, 10, 10)),
)
sim = Simulation(name=name, workspace=workspace, tdis=time)
gwf_name = "mymodel"
ims = Ims(parent=sim, models=[gwf_name])  # temporary hack
gwf = Gwf(parent=sim, name=gwf_name, save_flows=True, dis=grid)
npf = Npf(parent=gwf, save_specific_discharge=True)
chd = Chd(
    parent=gwf,
    head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}},
)
ic = Ic(parent=gwf, strt=1.0)
oc = Oc(
    parent=gwf,
    budget_file=f"{gwf.name}.bud",
    head_file=f"{gwf.name}.hds",
    save_head={0: "all"},
    save_budget={0: "all"},
)

sim.write()
sim.run(verbose=True)

assert chd.data["head"][0, 0] == 1.0
assert chd.data.head.sel(per=0)[99] == 0.0
assert np.allclose(chd.data.head[:, 1:99], np.full(98, 1e30))

assert gwf.dis.data.botm.sel(lay=0, col=0, row=0) == 0.0

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
