"""The values period arrays hold in each stress period, as MF6 holds them in
its input context. See ``flopy4.mf6.period_arrays`` for how period arrays
are given.

This module knows nothing of packages: it takes period blocks, ``{kper:
{tag: value}}``, and returns ``{tag: (nper, ...) array}``. A tag names one
array (a stress field, or one auxiliary variable); the caller picks them.
`Package.period_states` and the NetCDF export both go through here.

How a period block changes the values depends on how MF6 reads the package
(`period_mode`):

- ``"layer"`` (RCHA, EVTA; READASARRAYS): an array given holds its values
  until given again. An array given as a time-array series holds no values
  (fill) while linked. The layer index array (IRCH, IEVT) holds 0 (1 in the
  file) until given.
- ``"grid"`` (CHDG, WELG, ...; READARRAYGRID): the first array given in a
  block, stress or aux, sets the block's boundary cells, the active cells
  where it has a value. MF6 stores each array by position in that list of
  cells, so an array not given keeps its values by position, at the new
  boundary cells. An empty block removes every boundary cell; the values
  stay stored, for the arrays a later block doesn't give. A position no
  block has written holds 0, as MF6 allocates the arrays.

An array never given holds ``FILL_DNODATA``.
"""

import warnings
from collections.abc import Mapping
from typing import Any, Literal, Optional

import attrs
import numpy as np

from flopy4.mf6._types import TimeArraySeriesRef
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.period_arrays import is_grid_package

Mode = Literal["layer", "grid"]


def period_mode(cls: type) -> Mode:
    """How MF6 reads a package class's period blocks."""
    if not is_grid_package(cls):
        return "layer"
    if "maxbound" not in attrs.fields_dict(cls):
        raise NotImplementedError(f"{cls.__name__}: full-grid period arrays (no MAXBOUND)")
    return "grid"


def _active(active: Optional[np.ndarray], size: int) -> np.ndarray:
    if active is None:
        return np.ones(size, dtype=bool)
    act = np.ravel(active)
    if act.size == 1:
        return np.broadcast_to(act, size)
    if act.size != size:
        raise ValueError(f"idomain has {act.size} cells, period arrays {size}")
    return act


def _grid_states(
    blocks: Mapping[int, Mapping[str, Any]],
    shapes: Mapping[str, tuple[int, ...]],
    nper: int,
    active: Optional[np.ndarray],
) -> dict[str, np.ndarray]:
    """Grid arrays' values in each period, read as MF6's grid-array loader
    reads them (Mf6FileGridArray.f90): by position in the block's list of
    boundary cells."""
    out = {t: np.full((nper, *s), FILL_DNODATA) for t, s in shapes.items()}
    if not shapes:
        return out
    size = int(np.prod(next(iter(shapes.values()))))
    act = _active(active, size)
    cells = np.zeros(0, dtype=np.int64)  # boundary cells, by position
    stored = {t: np.zeros(size) for t in shapes}
    given: set[str] = set()
    for kper in range(nper):
        if (blk := blocks.get(kper)) is not None:
            first = True
            cells = np.zeros(0, dtype=np.int64)
            for tag, v in blk.items():  # in the order written
                if v is None:
                    continue
                if isinstance(v, TimeArraySeriesRef):
                    raise NotImplementedError(f"{tag}: time-array series grid arrays")
                a = np.broadcast_to(np.asarray(v, dtype=float), shapes[tag]).ravel()
                if first:
                    cells = np.flatnonzero((a != FILL_DNODATA) & act)
                    first = False
                stored[tag][: cells.size] = a[cells]
                given.add(tag)
        for tag in given:
            out[tag][kper].reshape(-1)[cells] = stored[tag][: cells.size]
    return out


def _layer_states(
    blocks: Mapping[int, Mapping[str, Any]],
    shapes: Mapping[str, tuple[int, ...]],
    nper: int,
    index: Optional[str],
) -> dict[str, np.ndarray]:
    """Layer arrays' values in each period: each array holds what it was
    last given."""
    out = {
        t: np.zeros((nper, *s), dtype=np.int64) if t == index else np.full((nper, *s), FILL_DNODATA)
        for t, s in shapes.items()
    }
    held: dict[str, Any] = {}
    for kper in range(nper):
        for tag, v in (blocks.get(kper) or {}).items():
            # a series-linked array holds no values
            held[tag] = None if isinstance(v, TimeArraySeriesRef) else v
        for tag, v in held.items():
            out[tag][kper] = FILL_DNODATA if v is None else np.broadcast_to(v, shapes[tag])
    return out


def period_states(
    blocks: Mapping[int, Mapping[str, Any]],
    mode: Mode,
    nper: int,
    shapes: Mapping[str, tuple[int, ...]],
    active: Optional[np.ndarray] = None,
    index: Optional[str] = None,
) -> dict[str, np.ndarray]:
    """The values each array holds in each period, ``{tag: (nper, ...)
    array}``, ``FILL_DNODATA`` where it holds none.

    ``blocks`` holds the period blocks as written, ``{kper: {tag: value}}``,
    each block's tags in the order they're written (in a grid block, the
    first array sets the boundary cells). ``shapes`` gives the shape of
    every tag in one period, including tags no block gives. ``active``
    (flat, by user node) marks the active cells, for grid arrays. ``index``
    is the tag of a layer package's layer index array, if any.
    """
    if past := sorted(k for k in blocks if k >= nper):
        warnings.warn(f"periods {past} are past NPER ({nper}), dropped", stacklevel=2)
    if unknown := {t for b in blocks.values() for t in b} - set(shapes):
        raise ValueError(f"no shape for {sorted(unknown)}")
    if mode == "grid":
        return _grid_states(blocks, shapes, nper, active)
    return _layer_states(blocks, shapes, nper, index)
