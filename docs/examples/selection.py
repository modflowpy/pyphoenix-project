# # Selecting cells
#
# Model arrays, input and output alike, carry coordinates for where their
# cells are: `x` and `y` for cell centres, `z_top`, `z_bot` and `z` for
# their elevations, and on a rotated grid, `x_world` and `y_world`. This
# guide shows how to select cells by those coordinates, and where
# selection works differently from what you might expect from xarray.
#
# * `sel` by `x`/`y` picks the cell *containing* a point, not the nearest
#   centre
# * lists select every combination of `x` and `y` (an outer product);
#   DataArrays on a shared dim select one cell per point
# * elevations: `.grid.sel_world(x, y, z)`, `.grid.sel_z(z)` and
#   `.grid.mask_z(zmin, zmax)`
# * rotated grids: `x`/`y` are in the grid's own frame, so select by world
#   coordinates with `.grid.sel_world`, or mask on `x_world`/`y_world`

# ### Imports

from pathlib import Path

import numpy as np
import xarray as xr

from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.time import Time

# ### Setup

try:
    SEL_ROOT = Path(__file__).parent
except NameError:
    SEL_ROOT = Path.cwd()

name = "selection"
workspace = SEL_ROOT / name
workspace.mkdir(exist_ok=True)

# ### A small model
#
# Three layers on a 4-row, 5-column grid of 10 m cells. The land surface
# slopes from 30 m in the west to 20 m in the east, and so do the bottoms
# of the top two layers, so the same elevation is in different layers in
# different columns. Constant heads on the west and east edges drive flow
# across the grid.

nlay, nrow, ncol = 3, 4, 5
top = np.tile(np.linspace(30.0, 20.0, ncol), (nrow, 1))
botm = np.stack([top - 10.0, top - 20.0, np.full((nrow, ncol), -10.0)])
dis = Dis(nlay=nlay, nrow=nrow, ncol=ncol, delr=10.0, delc=10.0, top=top, botm=botm)

sim = Simulation(name=name, workspace=workspace, tdis=Time(perlen=[1.0], nstp=[1]))
Ims(parent=sim, models=[name])
gwf = Gwf(parent=sim, name=name, save_flows=True, dis=dis)
Ic(parent=gwf, strt=20.0)
Npf(parent=gwf, k=1.0)
west = [((0, r, 0), 25.0) for r in range(nrow)]
east = [((0, r, ncol - 1), 15.0) for r in range(nrow)]
Chd(parent=gwf, stress_period_data={0: west + east})
Oc(
    parent=gwf,
    budget_file=f"{name}.cbc",
    head_file=f"{name}.hds",
    stress_period_data={0: [("SAVE", "HEAD", "ALL"), ("SAVE", "BUDGET", "ALL")]},
)
sim.write()
sim.run()

# Heads are on `(time, layer, row, col)`. `x` and `y` are the cell
# centres, on `col` and `row`; `z_top`, `z_bot` and `z` are each cell's
# top, bottom and centre, on `(layer, row, col)`. Package arrays, like
# `gwf.dis.to_dataarray("botm")`, have the same coordinates.

head = gwf.output.head.isel(time=0)
head

# ### Selecting a point
#
# `sel` by `x` and `y` gives the cell containing the point. The cell
# centred at x=15 spans 10–20, so x=12 is in it, as is anything else in
# that range: there's no need for `method="nearest"`.

col = head.sel(x=12.0, y=33.0)
assert col.dims == ("layer",)
assert (col.x.item(), col.y.item()) == (15.0, 35.0)
col

# The result is a *vertical column*: the cells at one row and column
# through all layers.
#
# A point on the edge between two cells gets the one with the lower
# index: the west cell for x, the north cell for y. That's what flopy's
# `StructuredGrid.intersect` does too.

assert head.sel(x=10.0, y=30.0).x.item() == 5.0  # west of the edge
assert head.sel(x=10.0, y=30.0).y.item() == 35.0  # north of the edge

# A point outside the grid raises `KeyError`, rather than giving the
# nearest cell on the grid's edge.

try:
    head.sel(x=60.0, y=5.0)
except KeyError as e:
    print("KeyError:", e)

# ### Several points: lists vs. DataArrays
#
# This is where selection is easiest to get wrong. Lists of x and y select
# every combination of them, as xarray does for any coordinates: two x's
# and two y's give 2 × 2 = 4 vertical columns.

xs, ys = [5.0, 25.0], [5.0, 35.0]
outer = head.sel(x=xs, y=ys)
assert outer.dims == ("layer", "row", "col")
assert outer.shape == (3, 2, 2)

# To select one cell per point, pass x and y as DataArrays on a shared
# dim. Each point gets its own vertical column, and the result is on that
# dim instead of `row` and `col`. This is xarray's
# [vectorized indexing](https://docs.xarray.dev/en/stable/user-guide/indexing.html#vectorized-indexing).
# The dim's name is up to you: `point` here, as in xarray's own examples
# (`points`), but `well` or `obs` work just as well.

px = xr.DataArray(xs, dims="point")
py = xr.DataArray(ys, dims="point")
points = head.sel(x=px, y=py)
assert points.dims == ("layer", "point")
assert points.shape == (3, 2)
assert points.x.values.tolist() == xs
assert points.y.values.tolist() == ys
points

# ### Selecting by elevation
#
# `sel` only works through an index. `x` and `y` have one, since each is
# 1-D, on `col` or `row`. `z` doesn't: cells' tops and bottoms vary from
# vertical column to vertical column, so it's on `(layer, row, col)`, and
# xarray's default index only takes 1-D coordinates. So `head.sel(z=...)`
# raises `KeyError`, alone or with `x` and `y`, even on a single vertical
# column.

try:
    head.sel(x=12.0, y=33.0, z=15.0)
except KeyError as e:
    print("KeyError:", e)

# The `.grid` accessor selects by elevation instead, from the arrays'
# `z_top` and `z_bot` coordinates.
#
# `.grid.sel_world(x, y, z)` gives the cell containing a point in 3D: the
# vertical column at x/y, then the cell in it whose top and bottom
# bracket z. In the column at x=15, layer 0 spans 27.5–17.5 m and layer 1
# 17.5–7.5 m, so z=15 is in layer 1. The chosen layer is kept as a
# `layer` coordinate.

cell = head.grid.sel_world(12.0, 33.0, 15.0)
assert cell.layer.item() == 1
assert (cell.z_top.item(), cell.z_bot.item()) == (17.5, 7.5)
cell

# An elevation on the interface between two layers goes to the upper one,
# as with x and y. An elevation above the top or below the bottom raises
# `KeyError`.

assert head.grid.sel_world(12.0, 33.0, 17.5).layer.item() == 0
try:
    head.grid.sel_world(12.0, 33.0, 40.0)
except KeyError as e:
    print("KeyError:", e)

# For several points, pass z as a DataArray on the same dim as x and y:
# each point gets its own cell.

pz = xr.DataArray([0.0, 24.0], dims="point")
cells = head.grid.sel_world(px, py, pz)
assert cells.dims == ("point",)
assert cells.layer.values.tolist() == [2, 0]
cells

# A scalar z with point x and y uses the same elevation at every point.
# Since the layers slope, z=16 is in a different layer at each point.

cells = head.grid.sel_world(px, py, 16.0)
assert cells.layer.values.tolist() == [1, 0]

# ### Horizontal slices and masks
#
# `.grid.sel_z(z)` selects z from every vertical column: a horizontal
# slice through the grid, on `(row, col)`. Again the layer differs from
# column to column, so the slice is a cell from layer 1 in the west and
# layer 0 in the east. Where z is above the top or below the bottom of a
# vertical column, the slice is NaN.

slice_15 = head.grid.sel_z(15.0)
assert slice_15.dims == ("row", "col")
assert slice_15.layer.values[0].tolist() == [1, 1, 0, 0, 0]
assert np.isnan(head.grid.sel_z(28.0).values[0]).tolist() == [False, True, True, True, True]
slice_15.layer

# `.grid.mask_z(zmin, zmax)` gives which cells are in an elevation range,
# as a boolean on `(layer, row, col)`, for use with `where`. By default a
# cell is in the range if it overlaps it; `how="within"` takes only cells
# entirely in the range, and `how="center"` cells whose centre is in it.

mask = head.grid.mask_z(12.0, 18.0)
assert mask.dims == ("layer", "row", "col")
assert mask.values[:, 0].astype(int).tolist() == [[0, 1, 1, 1, 1], [1, 1, 1, 1, 0], [0] * 5]
head.where(mask)

# ### Rotated grids
#
# A rotated grid's `x` and `y` are in the grid's own frame, measured from
# its lower-left corner, so that they stay 1-D on `col` and `row`. Its
# world coordinates are `x_world` and `y_world`, on `(row, col)`. Here's
# the same grid, moved to (1000, 2000) and rotated 30° counter-clockwise.
# Package arrays don't need a run, so this uses DIS's `botm`.

rotated = Dis(
    nlay=nlay,
    nrow=nrow,
    ncol=ncol,
    delr=10.0,
    delc=10.0,
    top=top,
    botm=botm,
    xorigin=1000.0,
    yorigin=2000.0,
    angrot=30.0,
)
bot = Gwf(dis=rotated).dis.to_dataarray("botm")
assert bot.x.values.tolist() == head.x.values.tolist()
assert bot.x_world.dims == ("row", "col")
bot

# `sel` by world coordinates fails, since they're outside the grid's own
# frame. `.grid.sel_world` converts them first.

xw, yw = float(bot.x_world[0, 1]), float(bot.y_world[0, 1])
try:
    bot.sel(x=xw, y=yw)
except KeyError as e:
    print("KeyError:", e)
col = bot.grid.sel_world(xw, yw)
assert (col.x.item(), col.y.item()) == (15.0, 35.0)

# For several points on a rotated grid, use DataArrays on a shared dim.
# Lists raise `ValueError`: every combination of world x's and y's isn't
# a set of rows and columns, since the grid's rows and columns don't run
# along world x and y.

xws = [float(bot.x_world[0, 1]), float(bot.x_world[2, 3])]
yws = [float(bot.y_world[0, 1]), float(bot.y_world[2, 3])]
try:
    bot.grid.sel_world(xws, yws)
except ValueError as e:
    print("ValueError:", e)
pts = bot.grid.sel_world(xr.DataArray(xws, dims="point"), xr.DataArray(yws, dims="point"))
assert pts.x.values.tolist() == [15.0, 35.0]
assert pts.y.values.tolist() == [35.0, 15.0]

# For the same reason, a range of world x or y isn't a range of rows or
# columns, so slices raise `ValueError` too. Mask on `x_world` and
# `y_world` instead.

try:
    bot.grid.sel_world(slice(1020.0, None), slice(None, None))
except ValueError as e:
    print("ValueError:", e)
in_east = bot.x_world >= 1020.0
assert in_east.dims == ("row", "col")
bot.where(in_east)
