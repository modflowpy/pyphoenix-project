import os

import cartopy.crs as ccrs
import flopy
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.collections import PolyCollection

QS_ROOT = os.path.abspath(os.path.join(__file__, ".."))
modelname = "mymodel"
ws = os.path.join(QS_ROOT, "quickstart_data")


def _pcolormesh(grid, da, ax):
    vertices = []
    for face in grid.iverts:
        f = []
        for i in face:
            f.append(grid.verts[i])
        vertices.append(f)
    vertices = np.array(vertices)

    collection = PolyCollection(vertices)
    collection.set_array(da.to_numpy().ravel())
    p = ax.add_collection(collection, autolim=False)

    xmin, xmax, ymin, ymax = grid.extent
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    cverts = (xmin, ymin), (xmax, ymax)
    ax.update_datalim(cverts)

    return p


# create budget reader
bpth = os.path.join(ws, f"{modelname}.bud")
bobj = flopy.utils.CellBudgetFile(bpth, precision="double")

# set specific discharge
spdis = bobj.get_data(text="DATA-SPDIS")[0]

# create head reader
hpth = os.path.join(ws, f"{modelname}.hds")
hobj = flopy.utils.HeadFile(hpth, precision="double")

# set heads
heads = hobj.get_alldata()

# create grb reader
grbpth = os.path.join(ws, f"{modelname}.dis.grb")
grbobj = flopy.mf6.utils.MfGrdFile(grbpth)
grid = None

# flow vector component arrays
uflow = None
vflow = None

# create grid object
if "NROW" in grbobj._datadict and "NCOL" in grbobj._datadict:
    grid = flopy.discretization.StructuredGrid.from_binary_grid_file(grbpth)
    u = []
    v = []
    for r in spdis:
        u.append(r[3])
        v.append(r[4])
    uflow = np.array(u).reshape(grid.nrow, grid.ncol)
    vflow = np.array(v).reshape(grid.nrow, grid.ncol)
else:
    raise Exception("unsupported discretization")

# set data coordinate arrays
xcrs = grid.xycenters[0]
ycrs = grid.xycenters[1]

# create qx, qy dataarrys
qx = xr.DataArray(uflow, dims=("y", "x"), coords={"x": xcrs, "y": ycrs})
qy = xr.DataArray(vflow, dims=("y", "x"), coords={"x": xcrs, "y": ycrs})

# create head data array
da = xr.DataArray(
    heads[0][0],
    dims=("y", "x"),
    coords={"x": xcrs, "y": ycrs},
    name="head",
)

# quickstart mesh with contours and flow arrows
fig, ax = plt.subplots()
_pcolormesh(grid, da, ax)
qz = np.sin(np.sqrt(uflow**2 + vflow**2))
plt.quiver(xcrs, ycrs, qx, qy, color="w")
cbar = plt.colorbar(label=da.name)
plt.contour(xcrs, ycrs, qz, 4, cmap="viridis")
# plt.contourf(xcrs, ycrs, qz, 5, cmap='viridis', alpha=0.4)
qs_pth = os.path.join(QS_ROOT, "image", "qs.png")
fig.savefig(qs_pth)

# projection example with cartopy
fig, ax = plt.subplots(subplot_kw={"projection": ccrs.PlateCarree()})
da.plot(ax=ax, transform=ccrs.PlateCarree())
ax.coastlines()
ax.stock_img()
ax.set_extent([-5, 15, -4, 14], crs=ccrs.PlateCarree())
gln = ax.gridlines(draw_labels=True)
gln.top_labels = False
gln.right_labels = False
ax.set_title("Head")
qsprj_pth = os.path.join(QS_ROOT, "image", "qsprj.png")
fig.savefig(qsprj_pth)
