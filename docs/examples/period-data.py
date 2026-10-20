# # Period data
#
# MODFLOW 6 stress packages take their period data in one of two forms:
#
# * **lists** (CHD, WEL, DRN, RIV, GHB, RCH, EVT, ...): a period block has a row
#   per boundary feature, naming its cell and giving its values;
# * **arrays** (CHDG, WELG, RCHA, EVTA, ...): a period block has a value per
#   cell of the grid.

# ### Imports

from pathlib import Path

import numpy as np
import pandas as pd

from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.gwf import Chd, Evt, Gwf, Ic, Npf, Oc, Wel
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.grid import StructuredGrid
from flopy4.mf6.utils.time import Time
from flopy4.mf6.utl import Ts

# ### A small model
#
# One layer of 3 rows and 4 columns, run for 3 stress periods. Packages
# attached to the model get their dimensions from it.

try:
    workspace = Path(__file__).parent / "period-data"
except NameError:
    workspace = Path.cwd() / "period-data"
workspace.mkdir(exist_ok=True)

grid = StructuredGrid(
    nlay=1,
    nrow=3,
    ncol=4,
    delr=np.ones(4),
    delc=np.ones(3),
    top=np.ones((3, 4)),
    botm=np.zeros((1, 3, 4)),
)
sim = Simulation(name="period-data", workspace=workspace, tdis=Time(perlen=[1.0] * 3, nstp=[1] * 3))
gwf = Gwf(parent=sim, name="model", dis=grid)

# ### Rows
#
# Period data maps each (0-based) period to its rows. A row is a tuple of the
# package's columns, in MF6 input guide order: for WEL, the cell, `q`, the
# auxiliary values and the boundname.
#
# A string in place of a number names a time series, which a TS6 file
# attached with `ts=` must define. Here `pumping` goes from -1 to -3 over the
# simulation.

pumping = Ts.from_series(pd.Series([-1.0, -3.0], index=[0.0, 3.0], name="pumping"))

# Periods fill forward: a period without a block repeats the last one, and an
# empty list turns every feature off. Here period 1 fills forward from period
# 0, and period 2 has two wells in one cell.

wel = Wel(
    parent=gwf,
    auxiliary=["conc"],
    boundnames=True,
    ts=[pumping],
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

# Rows come back as `Wel.StressPeriodData` objects, which can also be built
# by name.

row = wel.stress_period_data[0][0]
print(row)
assert row.q == -1.0 and row.aux == (5.0,) and row.boundname == "north"
assert row == Wel.StressPeriodData(cellid=(0, 0, 0), q=-1.0, aux=(5.0,), boundname="north")
assert str(wel.stress_period_data[0][1].q) == "pumping"
assert list(wel.stress_period_data) == [0, 2]

# ### The array view
#
# `to_xarray()` gives a variable per value column on `(per, layer, row, col)`,
# with every period filled forward. Empty cells hold `FILL_DNODATA` (3e30).
#
# * Each auxiliary variable is its own variable (`conc`).
# * Boundnames are a `boundname` coordinate.
# * A time series value is NaN, with its name in a `<var>_ts` coordinate.
#
# Two rows in one cell raise by default; here they're summed.

ds = wel.to_xarray(duplicates="sum")
ds

# +
q = ds["q"]
assert q.dims == ("per", "layer", "row", "col")
assert q[1, 0, 0, 0] == -1.0  # period 1 filled forward from period 0
assert q[0, 0, 1, 1] == FILL_DNODATA  # no well here until period 2
assert q[2, 0, 1, 1] == -2.5  # two wells, summed
assert ds["conc"][0, 0, 0, 0] == 5.0
assert ds["boundname"][0, 0, 0, 0] == "north"

assert np.isnan(q[0, 0, 2, 3])  # a time series value...
assert ds["q_ts"][0, 0, 2, 3] == "pumping"  # ...and its name
# -

# Use `ds["head"]`, not `ds.head`, which is xarray's `Dataset.head()`.
#
# ### Editing and writing back
#
# Edit the arrays, then pass the dataset to `from_xarray()`.

edited = ds.copy(deep=True)
edited["q"][1, 0, 0, 0] = -2.0
wel.from_xarray(edited)

# `from_xarray()` writes a block only where a period changes, so period 1
# now has its own block, and period 2's wells come back as one summed well.

for kper, rows in wel.stress_period_data.items():
    print(kper, rows)
assert list(wel.stress_period_data) == [0, 1, 2]
assert wel.stress_period_data[1][0].q == -2.0
assert len(wel.stress_period_data[2]) == 1

# Summing adds auxiliary values too, and keeps the last row's boundname.

assert wel.stress_period_data[2][0].aux == (3.0,)
assert wel.stress_period_data[2][0].boundname == "east-2"

# To add a feature, set all of its variables at the cell. Setting only some
# raises an error naming the missing one.

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
# * `duplicates="sum"`, `"first"` or `"last"` merges them. `"sum"` can't sum
#   a time series. The boundname kept is the first row's for `"first"`, the
#   last row's otherwise.
# * `sparse=True` keeps every row, on an `entry` dim with the period and cell
#   as coordinates. This also suits packages without a single cell per row
#   (HFB, MVR, OC).

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
# With `nseg` segments, each EVT row gives `nseg - 1` depth (`pxdp`) and rate
# (`petm`) proportions as tuples.

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

# In the array view these get an extra `nseg-1` dim. A cell needs all of its
# segment values.

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

# ### Writing and running
#
# To run, the model needs a solver, NPF and initial conditions, and here a
# constant head to supply the wells.

Ims(parent=sim, models=[gwf])
gwf.npf = Npf()
gwf.ic = Ic(strt=1.0)
Chd(parent=gwf, stress_period_data={0: [((0, 0, 3), 1.0)]})
gwf.oc = Oc(head_file=f"{gwf.name}.hds", stress_period_data={0: [("SAVE", "HEAD", "ALL")]})
sim.write()
sim.run()

# ### Lists or arrays?
#
# The rows remain the package's data; the array view is for working with it.
# For a stress over most of the grid, like recharge, an array package (RCHA,
# EVTA, CHDG, WELG, ...) is smaller and faster to write. For features in a
# few cells, use a list package. Only list packages support several features
# per cell, boundnames and EVT segments.
