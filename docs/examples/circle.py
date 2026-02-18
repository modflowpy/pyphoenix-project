# Circle
#
# Import dependencies.

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
import xugrid as xu
from flopy.mf6.utils.binarygrid_util import MfGrdFile

import flopy4

# Timing
time = flopy4.mf6.utils.time.Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="days")
nper = time.nper

grb_fpth = Path(__file__).parent / "data" / "circle" / "disv.disv.grb"
grb_obj = MfGrdFile(grb_fpth, verbose=True)
idomain = grb_obj.idomain
xorigin = grb_obj.xorigin
yorigin = grb_obj.yorigin
angrot = grb_obj.angrot

nlay, ncpl = int(grb_obj.nlay), int(grb_obj.ncpl)
top = np.ravel(grb_obj.top)
botm = grb_obj.bot
botm.shape = (nlay, ncpl)
vertices, cell2d = grb_obj.cell2d

LAYER_NODATA = np.full((ncpl), flopy4.mf6.constants.FILL_DNODATA, dtype=float)
GRID_NODATA = np.full((nlay, ncpl), flopy4.mf6.constants.FILL_DNODATA, dtype=float)

# TODO: xoff, yoff, angrot, crs, etc
disv = flopy4.mf6.gwf.disv.Disv(
    length_units="meters",
    nlay=nlay,
    ncpl=ncpl,
    nvert=len(vertices),
    top=top,
    botm=botm,
    idomain=idomain.reshape(nlay, ncpl),
    iv=np.array([v[0] for v in vertices], dtype=int),
    xv=np.array([v[1] for v in vertices], dtype=float),
    yv=np.array([v[2] for v in vertices], dtype=float),
    cell2ddata=flopy4.mf6.gwf.disv.Disv.grid_to_disv_cell2d(cell2d),
)

# generate xugrid mesh2d grid
grid = disv.to_grid().ugrid

# set dims
dims = {"nper": nper, "nlay": nlay, "ncpl": ncpl, "nvert": len(vertices), "nodes": nlay * ncpl}

# convert idomain to UgridDataArray
idomain = xu.UgridDataArray(
    xr.DataArray(
        idomain.reshape(nlay, ncpl),
        coords={"layer": [l + 1 for l in range(nlay)]},
        dims=["layer", grid.face_dimension],
    ),
    grid=grid,
)

# Create workspace
workspace = Path(__file__).parent / "circle" / "list"
workspace.mkdir(parents=True, exist_ok=True)

# plot the grid
fig, ax = plt.subplots()
xu.plot.line(grid, ax=ax)
ax.set_aspect(1)
plt.savefig(workspace / "grid.png", dpi=1200, bbox_inches="tight")
plt.close()

# Initial conditions
ic = flopy4.mf6.gwf.Ic(strt=0.0, dims=dims)

# Node properties
icelltype = xu.full_like(idomain, 0)
k = xu.full_like(idomain, 1.0, dtype=float)
k33 = k.copy()
npf = flopy4.mf6.gwf.Npf(
    save_specific_discharge=True,
    icelltype=icelltype.values.ravel(),
    k=k.values.ravel(),
    k33=k33.values.ravel(),
    # save_flows=True,
    dims=dims,
)

# Storage
sto = flopy4.mf6.gwf.Sto(
    ss=1.0e-5,
    sy=0.15,
    steady_state=[True],
    iconvert=0,
    dims=dims,
)

# Constant Head
chd_head = {}
chd_location = xu.zeros_like(idomain.sel(layer=2), dtype=bool).ugrid.binary_dilation(
    border_value=True
)
for i in np.where(chd_location)[0]:
    chd_head[(1, int(i))] = 1.0
chd = flopy4.mf6.gwf.Chd(
    head={"*": chd_head},
    print_input=True,
    print_flows=True,
    # save_flows=True,
    dims=dims,
)

constant_head = xu.full_like(idomain.sel(layer=2), 1.0, dtype=float).where(chd_location)
fig, ax = plt.subplots()
constant_head.ugrid.plot(ax=ax)
xu.plot.line(grid, ax=ax, color="black")
ax.set_aspect(1)
plt.savefig(workspace / "chd.png", dpi=1200, bbox_inches="tight")
plt.close()

# Recharge
rch = flopy4.mf6.gwf.Rch(recharge={"*": {(0, j): 0.001 for j in range(ncpl)}}, dims=dims)

# Output control
oc = flopy4.mf6.gwf.Oc(
    budget_file="gwf.bud",
    head_file="gwf.hds",
    save_head={0: "all"},
    save_budget={0: "all"},
    dims=dims,
)

# Flow model
gwf = flopy4.mf6.gwf.Gwf(
    save_flows=True,
    dis=disv,
    ic=ic,
    npf=npf,
    sto=sto,
    chd=[chd],
    rch=[rch],
    oc=oc,
)
# gwf.netcdf_mesh2d_file = Path("circle.nc")

ims = flopy4.mf6.Ims(
    print_option="summary",
    outer_dvclose=1.0e-4,
    outer_maximum=500,
    under_relaxation=None,
    inner_dvclose=1.0e-4,
    inner_rclose=0.001,
    inner_maximum=100,
    linear_acceleration="cg",
    reordering_method=None,
    relaxation_factor=0.97,
    models=["gwf"],
)

# TDIS
tdis = flopy4.mf6.simulation.Tdis.from_time(time)

# Create simulation
sim = flopy4.mf6.simulation.Simulation(
    name="circle",
    tdis=tdis,
    models={"gwf": gwf},
    solutions={"ims": ims},
    workspace=workspace,
)

# Write input files and run the simulation
sim.write()
sim.run()  # assumes the ``mf6`` executable is available on your PATH.


#####################
head = gwf.output.head
cbc = gwf.output.budget
# from flopy.utils import HeadFile
# hds = HeadFile(workspace / "gwf.hds", precision="double")

cbc_grid = cbc["flow-horizontal-face-x"].grid
ds = xu.UgridDataset(grids=cbc_grid)
ds["u"] = cbc["flow-horizontal-face-x"]
ds["v"] = cbc["flow-horizontal-face-y"]

# Visualize the results
ds = ds.ugrid.assign_edge_coords()
fig, ax = plt.subplots()
head.isel(time=0, layer=0).compute().ugrid.plot(ax=ax)
ds.isel(time=0, layer=0).plot.quiver(
    x="mesh2d_edge_x", y="mesh2d_edge_y", u="u", v="v", color="white"
)
ax.set_aspect(1)
plt.savefig(workspace / "head.png", dpi=1200, bbox_inches="tight")
plt.close()

# TODO
# convert mf6 netcdf dependent layered var to head dataarray
# import pandas as pd
# mf6_heads_ds = xu.open_dataset(workspace / "circle.nc")
# layer_vars = []
# layer_labels = []
# for l in range(nlay):
#    layer_labels.append(f"HEAD layer {l + 1}")
#    layer_vars.append(mf6_heads_ds[f"head_l{l+1}"])


# new_dim_coords = pd.Index(layer_labels, name="layer")
# dep_da = xu.concat(layer_vars, dim=new_dim_coords)
# dep_da = dep_da.transpose('time', 'layer', 'nmesh_face').rename("head")
# dep_da.attrs["long_name"] = "head"
