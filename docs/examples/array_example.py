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

# This example demonstrates the `MFArray` class.

# +
from pathlib import Path

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

# Open and load a NumPy array representation

fhandle = open(internal)
imfa = MFArray.load(fhandle, data_path, shape)

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
cmfa = MFArray.load(fhandle, data_path, shape)
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
emfa = MFArray.load(fhandle, data_path, shape)
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
ilmfa = MFArray.load(fhandle, data_path, shape, layered=True)
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
clmfa = MFArray.load(fhandle, data_path, shape, layered=True)

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
mlmfa = MFArray.load(fhandle, data_path, shape, layered=True)

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
