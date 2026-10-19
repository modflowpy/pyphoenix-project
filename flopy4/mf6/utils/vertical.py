"""Selection by elevation. A vertical column is the cells at one
``(row, col)``, or one DISV ``cell``, through all layers. Layers in a
vertical column don't overlap, so an elevation is in at most one of its
cells: z picks a layer per vertical column, and with x/y, a cell. Cells'
tops and bottoms come from ``z_top``/``z_bot`` coordinates on the array's
cell dims (see ``z_coords``), or are passed in as DataArrays on those
dims.

Selection is geometric: inactive and pass-through cells are found like
any other, and their values are whatever the array holds there."""

from typing import Any

import numpy as np
import xarray as xr


def z_coords(top, botm, dims) -> dict[str, Any]:
    """Each cell's elevations from a discretization's ``top`` and
    ``botm``, as coordinates on ``dims``: ``z_top`` and ``z_bot``, its top
    and bottom, and ``z``, its centre. ``botm`` is shaped by ``dims``,
    ``(nlay, nrow, ncol)`` for DIS or ``(nlay, ncpl)`` for DISV, and
    ``top`` by a layer's cells, or is a scalar. A layer's top is the bottom
    of the layer above, and the first's is ``top``. Each has a
    ``long_name``, so an array's repr says they're its cells' elevations,
    not its values."""
    z_bot = np.asarray(botm, dtype=np.float64)
    top = np.asarray(top, dtype=np.float64)
    shape = z_bot.shape[1:]
    top = top.reshape(shape) if top.size == np.prod(shape) else np.broadcast_to(top, shape)
    z_top = np.concatenate([top[None], z_bot[:-1]])
    return {
        "z": (dims, (z_top + z_bot) / 2, {"long_name": "cell centre elevation"}),
        "z_top": (dims, z_top, {"long_name": "cell top elevation"}),
        "z_bot": (dims, z_bot, {"long_name": "cell bottom elevation"}),
    }


def _bounds(obj, z_top, z_bot, dim):
    if z_top is None:
        z_top = obj.coords.get("z_top")
    if z_bot is None:
        z_bot = obj.coords.get("z_bot")
    if z_top is None or z_bot is None:
        raise ValueError("no z_top/z_bot coordinates: pass them, or attach them")
    if dim not in z_top.dims or dim not in z_bot.dims:
        raise ValueError(f"z_top/z_bot have no {dim!r} dim")
    return z_top, z_bot


def layer_at(z, z_top, z_bot, dim="layer") -> tuple[xr.DataArray, xr.DataArray]:
    """The layer containing elevation ``z`` in each vertical column, as a
    position along ``dim``, and whether there is one; the position is 0
    where there isn't. ``z`` may be a scalar, or a DataArray on the
    vertical columns' dims or a points dim. A z on an interface goes to the
    upper (lower-numbered) layer, and the model's top and bottom are
    inclusive, as in flopy3's ``intersect``: layers are tested from the
    top, inclusive at both ends, and the first wins."""
    inside = (z_bot <= z) & (z <= z_top)
    return inside.argmax(dim), inside.any(dim)


def sel_z(obj, z, *, z_top=None, z_bot=None, dim="layer", outside="nan"):
    """Select from an array (or dataset) the cell containing elevation
    ``z`` in each vertical column. On a whole grid, this is a horizontal
    slice: ``dim`` is replaced by the containing layer per vertical
    column, e.g. ``(time, layer, row, col)`` to ``(time, row, col)``. On
    one vertical column, as from selecting by x/y, it's the cell at that
    elevation; for points, pass ``z`` as a DataArray sharing their dim.
    Ties go to the upper layer (see ``layer_at``).

    The chosen positions are kept as a ``dim`` coordinate. Vertical
    columns where no cell contains z (above the top or below the bottom)
    are NaN, as are their positions and the other coordinates that were
    on ``dim``; with ``outside="raise"``, they raise ``KeyError``."""
    if outside not in ("nan", "raise"):
        raise ValueError(f"outside must be 'nan' or 'raise', got {outside!r}")
    if dim not in obj.dims:
        raise ValueError(f"no {dim!r} dim to select from")
    z_top, z_bot = _bounds(obj, z_top, z_bot, dim)
    # Indexing needs concrete positions; bounds are small, so compute them
    # even if chunked along with the array.
    idx, found = (v.compute() for v in layer_at(z, z_top, z_bot, dim))
    complete = bool(found.all())
    if outside == "raise" and not complete:
        raise KeyError(f"no cell contains z={z}")
    on_dim = [k for k, v in obj.coords.items() if dim in v.dims]
    if isinstance(obj, xr.Dataset):
        on_dim += [k for k, v in obj.data_vars.items() if dim in v.dims]
    out = obj.isel({dim: idx})
    if not complete:
        masked = {k: out[k].where(found) for k in on_dim}
        if isinstance(out, xr.DataArray):
            out = out.where(found)
        else:
            out = out.assign({k: v for k, v in masked.items() if k in out.data_vars})
        out = out.assign_coords({k: v for k, v in masked.items() if k in out.coords})
        idx = idx.where(found)
    return out.assign_coords({dim: idx.variable})


def mask_z(obj, zmin=None, zmax=None, *, how="overlap", z_top=None, z_bot=None, dim="layer"):
    """Which cells are in the elevation range ``zmin``–``zmax``, as a
    boolean on the cells' dims, for ``obj.where(mask)``. A missing end is
    open. ``how`` is ``"overlap"``, the cell and range intersect over a
    positive length; ``"within"``, the cell is entirely in the range; or
    ``"center"``, the cell's centre (midway between its top and bottom)
    is in the range, inclusive."""
    zmin = -np.inf if zmin is None else zmin
    zmax = np.inf if zmax is None else zmax
    if zmin > zmax:
        raise ValueError(f"zmin {zmin} is above zmax {zmax}")
    z_top, z_bot = _bounds(obj, z_top, z_bot, dim)
    if how == "overlap":
        mask = (z_bot < zmax) & (z_top > zmin)
    elif how == "within":
        mask = (z_bot >= zmin) & (z_top <= zmax)
    elif how == "center":
        center = (z_top + z_bot) / 2
        mask = (center >= zmin) & (center <= zmax)
    else:
        raise ValueError(f"how must be 'overlap', 'within' or 'center', got {how!r}")
    return mask
