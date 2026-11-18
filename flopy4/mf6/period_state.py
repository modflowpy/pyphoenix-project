"""The values a package's period arrays hold in each stress period, as MF6
holds them in its input context, for export (NetCDF). See
``flopy4.mf6.period_arrays`` for how period arrays are given.

How a period block changes the values depends on how MF6 reads the package:

- Layer arrays (RCHA, EVTA; READASARRAYS): an array given holds its values
  until given again. An array given as a time-array series holds no values
  (fill) while linked. The layer index array (IRCH, IEVT) holds 1 until
  given.
- Grid arrays (CHDG, WELG, ...; READARRAYGRID): the first array given in a
  block, stress or aux, sets the block's boundary cells, the active cells
  where it has a value. MF6 stores each array by position in that list of
  cells, so an array not given keeps its values by position, at the new
  boundary cells. An empty block removes every boundary cell; the values
  stay stored, for the arrays a later block doesn't give. A position no
  block has written holds 0, as MF6 allocates the arrays.

An array never given holds ``FILL_DNODATA``.
"""

import warnings
from typing import Any, Optional

import attrs
import numpy as np

from flopy4.mf6._types import TimeArraySeriesRef
from flopy4.mf6.constants import FILL_DNODATA


def aux_names(package: Any) -> list[str]:
    """A package's auxiliary variable names, lowercase."""
    aux = getattr(package, "auxiliary", None)
    return [] if aux is None else [str(n).lower() for n in np.atleast_1d(aux)]


def _mode(cls: type) -> str:
    fields = attrs.fields_dict(cls)
    if "readarraygrid" not in fields:
        return "layer"
    if "maxbound" not in fields:
        raise NotImplementedError(f"{cls.__name__}: full-grid period arrays (no MAXBOUND)")
    return "grid"


def _grid_states(
    blocks: dict[int, dict[str, Any]],
    tags: list[str],
    nper: int,
    shape: Any,
    active: Optional[np.ndarray],
) -> dict[str, list[np.ndarray]]:
    """Grid arrays' values in each period, read as MF6's grid-array loader
    reads them (Mf6FileGridArray.f90): by position in the block's list of
    boundary cells."""
    size = int(np.prod(shape(tags[0]))) if tags else 0
    if active is None:
        act = np.ones(size, dtype=bool)
    else:
        act = np.ravel(active)
        if act.size == 1:
            act = np.broadcast_to(act, size)
        elif act.size != size:
            raise ValueError(f"idomain has {act.size} cells, period arrays {size}")
    cells = np.zeros(0, dtype=np.int64)  # boundary cells, by position
    stored = {t: np.zeros(size) for t in tags}
    given: set[str] = set()
    out: dict[str, list[np.ndarray]] = {t: [] for t in tags}
    for kper in range(nper):
        if (blk := blocks.get(kper)) is not None:
            first = True
            cells = np.zeros(0, dtype=np.int64)
            # in the order written: stress arrays as declared, then aux
            for tag, v in blk.items():
                if v is None:
                    continue
                if isinstance(v, TimeArraySeriesRef):
                    raise NotImplementedError(f"{tag}: time-array series grid arrays")
                a = np.broadcast_to(np.asarray(v, dtype=float), shape(tag)).ravel()
                if first:
                    cells = np.flatnonzero((a != FILL_DNODATA) & act)
                    first = False
                stored[tag][: cells.size] = a[cells]
                given.add(tag)
        for tag in tags:
            a = np.full(size, FILL_DNODATA)
            if tag in given:
                a[cells] = stored[tag][: cells.size]
            out[tag].append(a.reshape(shape(tag)))
    return out


def period_states(
    package: Any,
    nper: int,
    fields: list,
    shapes: dict[str, tuple[int, ...]],
    active: Optional[np.ndarray] = None,
) -> dict[str, list[np.ndarray]]:
    """The values each period array holds in each period: ``{tag:
    [array per period]}``, ``FILL_DNODATA`` where it holds no values. `fields`
    are the package's period array fields; tags are their names, and an aux
    field's are ``aux:<name>`` for each auxiliary name. `shapes` gives each
    field's period shape; `active` (flat, by user node) marks active cells
    for grid arrays."""
    mode = _mode(type(package))

    blocks: dict[int, dict[str, Any]] = {}
    tags: list[str] = []
    index = None
    for f in fields:
        value = package.__dict__.get(f.name) or {}
        if f.metadata.get("fk"):
            names = aux_names(package)
            tags += [f"aux:{n}" for n in names]
            for kper, arrays in value.items():
                for n, a in arrays.items():
                    blocks.setdefault(kper, {})[f"aux:{str(n).lower()}"] = a
        else:
            tags.append(f.name)
            if f.metadata.get("index"):
                index = f.name
            for kper, a in value.items():
                blocks.setdefault(kper, {})[f.name] = a

    if past := sorted(k for k in blocks if k >= nper):
        warnings.warn(f"periods {past} are past NPER ({nper}), dropped", stacklevel=3)

    def shape(tag: str) -> tuple[int, ...]:
        return shapes["aux" if tag.startswith("aux:") else tag]

    if mode == "grid":
        return _grid_states(blocks, tags, nper, shape, active)

    state: dict[str, Optional[np.ndarray]] = dict.fromkeys(tags)
    if index is not None:
        state[index] = np.zeros(shape(index), dtype=np.int64)
    out: dict[str, list[np.ndarray]] = {t: [] for t in tags}
    for kper in range(nper):
        for tag, v in (blocks.get(kper) or {}).items():
            # a series-linked array holds no values
            linked = isinstance(v, TimeArraySeriesRef)
            state[tag] = None if linked else np.broadcast_to(np.asarray(v), shape(tag))
        for tag in tags:
            a = state[tag]
            out[tag].append(np.full(shape(tag), FILL_DNODATA) if a is None else a)
    return out
