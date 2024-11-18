# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.16.2
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# # Array variables
#
# This example demonstrates how to work with array input variables.
#
# ## Overview
#
# FloPy works natively with NumPy arrays. Array input data can be provided
# as `ndarray` (or anything acting like one). FloPy also provides an array
# subclass `MFArray` supporting some special behaviors:
#
# - more efficient memory usage for constant arrays
# - convenient layered array manipulation
# - applying a multiplication factor
#
# TODO: rewrite the io stuff (external/internal) once that is moved to a
# separate layer from MFArray

# +
from pathlib import Path
from tempfile import TemporaryDirectory

import flopy
import git
import matplotlib.pyplot as plt
import numpy as np
import pooch

from flopy4.array import MFArray

# -

try:
    root = Path(git.Repo(".", search_parent_directories=True).working_dir)
except:
    root = None
workspace = root / "docs" / "examples" if root else Path.cwd()
data_path = workspace / "data" / "mfarray" if root else Path.cwd()

# non-layered data

fname = "internal.txt"
internal = pooch.retrieve(
    url=f"https://github.com/pyphoenix/pyphoenix-project/raw/develop/docs/examples/data/mfarray/{fname}",
    fname=fname,
    path=data_path,
    known_hash=None,
)
constant = data_path / "constant.txt"
external = data_path / "external.txt"
shape = (1000, 100)
dtype = "double"

# Open and load a NumPy array representation

fhandle = open(internal)
imfa = MFArray.load(fhandle, data_path, shape, type=dtype, header=False)

# Get values

ivals = imfa.value
plt.imshow(ivals[0:100])
plt.colorbar()

print(imfa.how)
print(imfa.factor)

imfa._value

# adjust values

imfa[0:8] = 5000
ivals2 = imfa.value
plt.imshow(ivals2[0:100])
plt.colorbar()

fhandle = open(constant)
cmfa = MFArray.load(fhandle, data_path, shape, type=dtype, header=False)
cvals = cmfa.value
plt.imshow(cvals[0:100])
plt.colorbar()

print(cmfa._value)

cmfa.how

# Slicing and multiplication

cmfa[0:10] *= 5
plt.imshow(cmfa[0:100])
plt.colorbar()

cmfa.how

cvals2 = cmfa.value
cmfa._value

# External

fhandle = open(external)
emfa = MFArray.load(fhandle, data_path, shape, type=dtype, header=False)
evals = emfa.value
evals

plt.imshow(emfa[0:100])
plt.colorbar()

emfa.how, emfa.factor

emfa **= 6
evals2 = emfa.value
evals2

plt.imshow(emfa[0:100])
plt.colorbar()

# #### Layered data
# layered data

ilayered = data_path / "internal_layered.txt"
clayered = data_path / "constant_layered.txt"
mlayered = data_path / "mixed_layered.txt"  # (internal, constant, external)

fhandle = open(ilayered)
shape = (3, 1000, 100)
ilmfa = MFArray.load(
    fhandle, data_path, shape, type=dtype, header=False, layered=True
)
vals = ilmfa.value

ilmfa._value  # internal storage

vals = ilmfa.value
vals

# +
fig, axs = plt.subplots(ncols=3, figsize=(12, 4))
vmin, vmax = np.min(vals), np.max(vals)
for ix, v in enumerate(vals):
    im = axs[ix].imshow(v[0:100], vmin=vmin, vmax=vmax)
    axs[ix].set_title(f"layer {ix + 1}")

fig.subplots_adjust(right=0.8)
cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
fig.colorbar(im, cax=cbar_ax)
# -

ilmfa.how

ilmfa.factor

# Adjust array values using ufuncs

ilmfa[0, 0:10, 0:60] += 350
ilmfa[1, 10:20, 20:80] += 350
ilmfa[2, 20:30, 40:] += 350

# +
vals = ilmfa.value
fig, axs = plt.subplots(ncols=3, figsize=(12, 4))
vmin, vmax = np.min(vals), np.max(vals)
for ix, v in enumerate(vals):
    im = axs[ix].imshow(v[0:100], vmin=vmin, vmax=vmax)
    axs[ix].set_title(f"layer {ix + 1}")

fig.subplots_adjust(right=0.8)
cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
fig.colorbar(im, cax=cbar_ax)
# -

# Layered constants

fhandle = open(clayered)
shape = (3, 1000, 100)
clmfa = MFArray.load(
    fhandle, data_path, shape, type=dtype, header=False, layered=True
)

clmfa._value

for obj in clmfa._value:
    print(obj._value)
clmfa.how

vals = clmfa.value

# +
fig, axs = plt.subplots(ncols=3, figsize=(12, 4))
vmin, vmax = np.min(vals), np.max(vals)
for ix, v in enumerate(vals):
    im = axs[ix].imshow(v[0:100], vmin=vmin, vmax=vmax)
    axs[ix].set_title(f"layer {ix + 1}")

fig.subplots_adjust(right=0.8)
cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
fig.colorbar(im, cax=cbar_ax)
# -

# Adjust a slice of the layered array

clmfa[0, 0:80, 20:80] += 10
clmfa[1] += 5
clmfa[2] += 2

clmfa.how

# verify that the constants haven't
# been converted to array internally
for obj in clmfa._value[1:]:
    print(obj._value)

vals = clmfa.value

# +
fig, axs = plt.subplots(ncols=3, figsize=(12, 4))
vmin, vmax = np.min(vals), np.max(vals)
for ix, v in enumerate(vals):
    im = axs[ix].imshow(v[0:100], vmin=vmin, vmax=vmax)
    axs[ix].set_title(f"layer {ix + 1}")

fig.subplots_adjust(right=0.8)
cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
fig.colorbar(im, cax=cbar_ax)
# -

# Mixed data source Layered

fhandle = open(mlayered)
shape = (3, 1000, 100)
mlmfa = MFArray.load(
    fhandle, data_path, shape, type=dtype, header=False, layered=True
)

mlmfa.how

mlmfa._value

vals = mlmfa.value
vals = np.where(vals <= 0, vals.mean(), vals)
mlmfa[:] = vals

# +
fig, axs = plt.subplots(ncols=3, figsize=(12, 4))
vmin, vmax = np.min(vals), np.max(vals)
for ix, v in enumerate(vals):
    im = axs[ix].imshow(v[0:100], vmin=vmin, vmax=vmax)
    axs[ix].set_title(f"layer {ix + 1}")

fig.subplots_adjust(right=0.8)
cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
fig.colorbar(im, cax=cbar_ax)
# -

# ### Using numpy mathematical functions
#
# Numpy support has been added to `MFArray` though the
# `__array_ufunc__`` mixin method. This method permits
# sending `MFArray` to standard NumPy functions, like
# `np.log()`, `np.sin()`, `np.pow()`, etc ...

mlmfa = np.log(mlmfa)
mlmfa

vals = mlmfa.value
vals

# +
fig, axs = plt.subplots(ncols=3, figsize=(12, 4))
vmin, vmax = np.min(vals), np.max(vals)
for ix, v in enumerate(vals):
    im = axs[ix].imshow(v[0:100], vmin=vmin, vmax=vmax)
    axs[ix].set_title(f"layer {ix + 1}")

fig.subplots_adjust(right=0.8)
cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
fig.colorbar(im, cax=cbar_ax)
# -

# We can also get statistical information about the data,
# like `sum()`, `mean()`, `max()`, `min()`, `median`, `std()`

mlmfa.sum()

mlmfa.min(), mlmfa.mean(), mlmfa.max()


# ## Grid-shaped array data
#
# Most MODFLOW array data are two (row, column) or three (layer,
# row, column) dimensional and represent data on the model grid.
# grid. Other MODFLOW array data contain data by stress period.
# The following list summarizes the types of MODFLOW array data.

# * Time-invariant multi-dimensional array data.  This includes:
#   1. One and two dimensional arrays that do not have a layer dimension.
#      Examples include `top`, `delc`, and `delr`.
#   2. Three dimensional arrays that can contain a layer dimension.
#      Examples include `botm`, `idomain`, and `k`.
# * Transient arrays that can change with time and therefore contain arrays of
#    data for one or more stress periods.  Examples include `irch` and
#    `recharge` in the `RCHA` package.
#
# In the example below a three dimensional ndarray is constructed for the
# `DIS` package's `botm` array.  First, the a simulation and groundwater-flow
# model are set up.

# set up where simulation workspace will be stored
temp_dir = TemporaryDirectory()
workspace = temp_dir.name
name = "grid_array_example"

# create the FloPy simulation and tdis objects
sim = flopy.mf6.MFSimulation(
    sim_name=name, exe_name="mf6", version="mf6", sim_ws=workspace
)
tdis = flopy.mf6.modflow.mftdis.ModflowTdis(
    sim,
    pname="tdis",
    time_units="DAYS",
    nper=2,
    perioddata=[(1.0, 1, 1.0), (1.0, 1, 1.0)],
)
# create the Flopy groundwater flow (gwf) model object
model_nam_file = f"{name}.nam"
gwf = flopy.mf6.ModflowGwf(sim, modelname=name, model_nam_file=model_nam_file)
# create the flopy iterative model solver (ims) package object
ims = flopy.mf6.modflow.mfims.ModflowIms(sim, pname="ims", complexity="SIMPLE")

# Then a three-dimensional ndarray of floating point values is created using
# numpy's `linspace` method.

bot = np.linspace(-50.0 / 3.0, -3.0, 3)
delrow = delcol = 4.0

# The `DIS` package is then created passing the three-dimensional array to the
# `botm` parameter.  The `botm` array defines the model's cell bottom
# elevations.

dis = flopy.mf6.modflow.mfgwfdis.ModflowGwfdis(
    gwf,
    pname="dis",
    nogrb=True,
    nlay=3,
    nrow=10,
    ncol=10,
    delr=delrow,
    delc=delcol,
    top=0.0,
    botm=bot,
)

# ## Adding MODFLOW Grid Array Data
# MODFLOW grid array data, like the data found in the `NPF` package's
# `GridData` block, can be specified as:
#
# 1. A constant value
# 2. A n-dimensional list
# 3. A numpy ndarray
#
# Additionally, layered grid data (generally arrays with a layer dimension) can
# be specified by layer.
#
# In the example below `icelltype` is specified as constants by layer, `k` is
# specified as a numpy ndarray, `k22` is specified as an array by layer, and
# `k33` is specified as a constant.

# First `k` is set up as a 3 layer, by 10 row, by 10 column array with all
# values set to 10.0 using numpy's full method.

k = np.full((3, 10, 10), 10.0)

# Next `k22` is set up as a three dimensional list of nested lists. This
# option can be useful for those that are familiar with python lists but are
# not familiar with the numpy library.

k22_row = []
for row in range(0, 10):
    k22_row.append(8.0)
k22_layer = []
for col in range(0, 10):
    k22_layer.append(k22_row)
k22 = [k22_layer, k22_layer, k22_layer]

# `K33` is set up as a single constant value.  Whenever an array has all the
# same values the easiest and most efficient way to set it up is as a constant
# value.  Constant values also take less space to store.

k33 = 1.0

# The `k`, `k22`, and `k33` values defined above are then passed in on
# construction of the npf package.

npf = flopy.mf6.ModflowGwfnpf(
    gwf,
    pname="npf",
    save_flows=True,
    icelltype=[1, 1, 1],
    k=k,
    k22=k22,
    k33=k33,
    xt3doptions="xt3d rhs",
    rewet_record="REWET WETFCT 1.0 IWETIT 1 IHDWET 0",
)

# ### Layered Data
#
# When we look at what will be written to the npf input file, we
# see that the entire `npf.k22` array is written as one long array with the
# number of values equal to `nlay` * `nrow` * `ncol`.  And this whole-array
# specification may be of use in some cases.  Often times, however, it is
# easier to work with each layer separately.  An `MFArray` object, such as
# `npf.k22` can be converted to a layered array as follows.

npf.k22.make_layered()

# By changing `npf.k22` to layered, we are then able to manage each layer
# separately.  Before doing so, however, we need to pass in data that can be
# separated into three layers.  An array of the correct size is one option.

shp = npf.k22.array.shape
a = np.arange(shp[0] * shp[1] * shp[2]).reshape(shp)
npf.k22 = a

# Now that `npf.k22` has been set to be layered, if we print information about
# it, we see that each layer is stored separately, however, `npf.k22.array`
# will still return a full three-dimensional array.

type(npf.k22)
npf.k22

# We also see that each layer is printed separately to the npf
# Package input file, and that the LAYERED keyword is activated:

npf.k22

# Working with a layered array provides lots of flexibility.  For example,
# constants can be set for some layers, but arrays for others:

npf.k22.set_data([1, a[2], 200])
npf.k22

# The array can be interacted with as usual for NumPy arrays:
npf.k22 = np.stack(
    [
        100 * np.ones((10, 10)),
        50 * np.ones((10, 10)),
        30 * np.ones((10, 10)),
    ]
)
npf.k22

# ## Adding MODFLOW Stress Period Array Data
# Transient array data spanning multiple stress periods must be specified as a
# dictionary of arrays, where the dictionary key is the stress period,
# expressed as a zero-based integer, and the dictionary value is the grid
# data for that stress period.

# In the following example a `RCHA` package is created.  First a dictionary
# is created that contains recharge for the model's two stress periods.
# Recharge is specified as a constant value in this example, though it could
# also be specified as a 3-dimensional ndarray or list of lists.

rch_sp1 = 0.01
rch_sp2 = 0.03
rch_spd = {0: rch_sp1, 1: rch_sp2}

# The `RCHA` package is created and the dictionary constructed above is passed
# in as the `recharge` parameter.

rch = flopy.mf6.ModflowGwfrcha(
    gwf, readasarrays=True, pname="rch", print_input=True, recharge=rch_spd
)

# Below the `NPF` `k` array is retrieved using the various methods highlighted
# above.

# First, view the `k` array.

npf.k

# `repr` gives a string representation of the data.

repr(npf.k)

# `str` gives a similar string representation of the data.

str(npf.k)

# Next, view the 4-dimensional array.

rch.recharge

# `repr` gives a string representation of the data.

repr(rch.recharge)

# str gives a similar representation of the data.

str(rch.recharge)
