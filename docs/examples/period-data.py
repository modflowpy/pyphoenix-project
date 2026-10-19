# # Period data
#
# MODFLOW 6 stress packages take their period data in one of two forms:
#
# * **lists** (CHD, WEL, DRN, RIV, GHB, RCH, EVT, ...): a period block has a row
#   per boundary feature, naming its cell and giving its values;
# * **arrays** (CHDG, WELG, RCHA, EVTA, ...): a period block has a value per
#   cell of the grid.
#
# flopy4 keeps each package in its MODFLOW 6 form. A list package holds rows,
# and `to_xarray()` gives the same data as grid-shaped arrays, to look at, plot
# or edit; `from_xarray()` turns the arrays back into rows.
#
# This page covers:
# * giving list data as rows, and how periods carry forward
# * auxiliary variables, boundnames and time series
# * the array view, and writing an edited array back
# * two features in one cell
# * columns with several values per row (EVT's segments)
# * when to use a list package and when an array package

# ### Imports

import numpy as np

from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.gwf import Evt, Gwf, Wel
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.grid import StructuredGrid
from flopy4.mf6.utils.time import Time

# ### A small model
#
# One layer of 3 rows and 4 columns, run for 3 stress periods. A package
# attached to the model gets the grid's and the time discretization's
# dimensions from it, which `to_xarray()` needs to place the rows.

grid = StructuredGrid(
    nlay=1,
    nrow=3,
    ncol=4,
    delr=np.ones(4),
    delc=np.ones(3),
    top=np.ones((3, 4)),
    botm=np.zeros((1, 3, 4)),
)
sim = Simulation(name="period-data", tdis=Time(perlen=[1.0] * 3, nstp=[1] * 3))
gwf = Gwf(parent=sim, name="model", dis=grid)

# ### Rows
#
# Period data is a dict from the (0-based) period to that period's rows. A
# row is a tuple of the package's columns, in the order the MF6 input guide
# lists them. For WEL with an auxiliary variable and boundnames, that is the
# cell, the rate `q`, a tuple with one value per auxiliary variable, and the
# name. A text value where a number goes names a time series (`"pumping"`
# below), which would be defined in the package's time series file.
#
# As in MF6, a period without a block repeats the last one, and an empty list
# turns every feature off. Here period 1 repeats period 0, and period 2
# replaces it with two wells in the same cell.

wel = Wel(
    parent=gwf,
    auxiliary=["conc"],
    boundnames=True,
    stress_period_data={
        0: [
            ((0, 0, 0), -1.0, (5.0,), "north"),
            ((0, 2, 3), "pumping", (0.0,), None),
        ],
        2: [
            ((0, 1, 1), -2.0, (1.0,), "east"),
            ((0, 1, 1), -0.5, (2.0,), "east-2"),
        ],
    },
)

# Each row comes back as an object with a field per column. Its class,
# `Wel.StressPeriodData`, can also be used to build rows by name instead of
# by position.

row = wel.stress_period_data[0][0]
print(row)
assert row.q == -1.0 and row.aux == (5.0,) and row.boundname == "north"
assert row == Wel.StressPeriodData(cellid=(0, 0, 0), q=-1.0, aux=(5.0,), boundname="north")
assert str(wel.stress_period_data[0][1].q) == "pumping"
assert list(wel.stress_period_data) == [0, 2]

# ### The array view
#
# `to_xarray()` gives a dataset with a variable per value column, on dims
# `(per, layer, row, col)`. All periods are there, with the carried-forward
# ones filled in. Cells without a feature hold `FILL_DNODATA` (3e30).
#
# * Each auxiliary variable is its own variable, named for it (`conc`).
# * Boundnames are a `boundname` coordinate.
# * A time series value is NaN, and the series' name is in a coordinate named
#   for the variable plus `_ts` (`q_ts`).
#
# Two rows in one cell can't share a grid position, so by default
# `to_xarray()` raises when it meets them. Here period 2's wells are summed;
# the next sections cover the other choices.

ds = wel.to_xarray(duplicates="sum")
ds

# +
q = ds["q"]
assert q.dims == ("per", "layer", "row", "col")
assert q[1, 0, 0, 0] == -1.0  # period 1 repeats period 0
assert q[0, 0, 1, 1] == FILL_DNODATA  # no well here until period 2
assert q[2, 0, 1, 1] == -2.5  # two wells, summed
assert ds["conc"][0, 0, 0, 0] == 5.0
assert ds["boundname"][0, 0, 0, 0] == "north"

assert np.isnan(q[0, 0, 2, 3])  # a time series value...
assert ds["q_ts"][0, 0, 2, 3] == "pumping"  # ...and its name
# -

# Use `ds["head"]`, not `ds.head`, for a variable called `head`: `ds.head` is
# xarray's `Dataset.head()` method.
#
# ### Editing and writing back
#
# Edit the arrays with any xarray or numpy operation, then give the dataset
# to `from_xarray()`. Here the north well pumps twice as hard in period 1.

edited = ds.copy(deep=True)
edited["q"][1, 0, 0, 0] = -2.0
wel.from_xarray(edited)

# `from_xarray()` writes a period block only where a period differs from the
# one before it, so the rows describe the same model as the arrays, but
# not necessarily with the same rows as before. Period 1 now has its own
# block, and period 2's two wells come back as the one summed well the
# arrays show.

for kper, rows in wel.stress_period_data.items():
    print(kper, rows)
assert list(wel.stress_period_data) == [0, 1, 2]
assert wel.stress_period_data[1][0].q == -2.0
assert len(wel.stress_period_data[2]) == 1

# Summing adds every value column, auxiliary variables too: the merged well's
# `conc` is 1.0 + 2.0, which suits a mass rate but not a concentration. The
# merged cell keeps the last row's boundname. Use `"first"`, `"last"` or
# `sparse=True` where a sum doesn't fit.

assert wel.stress_period_data[2][0].aux == (3.0,)

# A row needs every column. To add a feature in the array view, set all of
# its variables at the cell: `q` and `conc` here. Setting only some of them
# raises an error naming the missing column.

edited = wel.to_xarray()
edited["q"][0, 0, 2, 0] = -4.0
try:
    wel.from_xarray(edited)
except ValueError as e:
    print(e)
edited["conc"][0, 0, 2, 0] = 1.0
wel.from_xarray(edited)
assert len(wel.stress_period_data[0]) == 3

# ### Two features in one cell
#
# MF6 allows more than one row in a cell. When that happens, `to_xarray()`
# needs to be told what to do:
#
# * `duplicates="sum"`, `"first"` or `"last"` merges them into one value per
#   cell. A time series can't be summed.
# * `sparse=True` gives a row per entry instead of a grid: an `entry` dim, with
#   the period and the cell as coordinates. Every row is kept, and this form
#   also suits packages whose rows have no single cell (HFB, MVR, OC).

wel = Wel(
    parent=gwf,
    stress_period_data={0: [((0, 1, 1), -2.0), ((0, 1, 1), -0.5)]},
)
try:
    wel.to_xarray()
except ValueError as e:
    print(e)
assert wel.to_xarray(duplicates="last")["q"][0, 0, 1, 1] == -0.5

sparse = wel.to_xarray(sparse=True)
sparse

# +
assert sparse["q"].dims == ("entry",)
assert list(sparse["q"].values) == [-2.0, -0.5]
assert list(sparse["cellid_row"].values) == [1, 1]

expected = wel.stress_period_data
wel.from_xarray(sparse)
assert wel.stress_period_data == expected
# -

# ### Several values in one column
#
# A few columns hold more than one value per row: the auxiliary variables,
# and EVT's evapotranspiration segments. With `nseg` segments, each EVT row
# gives `nseg - 1` depth proportions (`pxdp`) and rate proportions (`petm`)
# as tuples.

evt = Evt(
    parent=gwf,
    nseg=3,
    stress_period_data={
        0: [
            # cell, surface, rate, depth, pxdp, petm
            ((0, 0, 0), 1.0, 0.1, 2.0, (0.3, 0.6), (0.5, 0.2)),
            ((0, 0, 1), 1.0, 0.1, 2.0, (0.4, 0.7), (0.6, 0.3)),
        ]
    },
)
assert evt.stress_period_data[0][0].pxdp == (0.3, 0.6)

# In the array view, such a column gets one more dim, named for its size,
# so each segment boundary is a grid of its own. Auxiliary variables instead
# get a variable per name, as above.

ds = evt.to_xarray()
pxdp = ds["pxdp"]
assert pxdp.dims == ("per", "nseg-1", "layer", "row", "col")
pxdp.isel(per=0, layer=0)

# +
np.testing.assert_array_equal(pxdp[0, :, 0, 0, 0], [0.3, 0.6])

expected = evt.stress_period_data
evt.from_xarray(ds)
assert evt.stress_period_data == expected
# -

# A cell needs all of its segment values, as it needs all of its other
# columns.

# ### Lists or arrays?
#
# The array view is for working with the data; the rows stay the package's
# data and what is written to its input file. For a stress that covers most
# of the grid, like recharge or evapotranspiration over a whole model, the
# array packages (RCHA, EVTA, and the CHDG, WELG, ... family) hold a grid per
# period directly and write it as an array, which is smaller and faster than
# a row per cell. In those packages each auxiliary variable is likewise its
# own array, and EVTA has no segments.
#
# For features in a few cells, like wells, drains or a river, the list
# packages are the natural fit. They also support what the array packages
# don't: more than one feature per cell, boundnames, and EVT's segments.
