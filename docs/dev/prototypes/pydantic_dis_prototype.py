"""
Pydantic prototype v3: ports `Dis` (flopy4/mf6/gwf/dis.py, via `DisBase` ->
`Package` -> `Component`) to pydantic, in its *current* (post-xattree,
post-Row-unification) shape.

v3 change from v2: built on `pydantic.dataclasses.dataclass`, not
`pydantic.BaseModel`. v2 (BaseModel) found no working analog to attrs'
`field(init=False)` (DisBase's derived nlay/nrow/ncol/ncpl/nvert/nodes) --
`Field(init=False)` on a `BaseModel` is accepted but has NO runtime effect
(confirmed: `M(nodes=999)` silently succeeds and sets `nodes=999`, even
under `extra="forbid"` -- it's type-checker-only metadata for BaseModel).
On a pydantic dataclass, the identical `Field(init=False)` DOES work at
runtime -- confirmed: with `extra="forbid"` in config, `M(nodes=999)`
raises `ValidationError: Unexpected keyword argument`, matching attrs'
own `TypeError: unexpected keyword argument` for the same case exactly.
See DisBaseProto below and the plan doc's "BaseModel vs. pydantic
dataclasses" section for the full comparison.

This exists to satisfy docs/dev/pydantic-object-model-plan.md's "next
steps when picked up": port one real, current-shape package end to end,
port its __attrs_post_init__/DimensionResolverMixin chain, and measure
ergonomics against the actual current codebase.

Mined from:
- flopy4/mf6/component.py, flopy4/mf6/package.py, flopy4/dimensions.py,
  flopy4/mf6/gwf/{dis,disbase}.py -- the mechanics being ported.
- origin/plan-codegen's pydantic_prototype.py (2026-01-23) -- the
  pydantic-side mechanics (Annotated NDArray hints, field_validator
  array-structuring pattern). Reused near-verbatim where still applicable.

Not wired into flopy4's real registry (FNAMES/FTYPES), codegen, or the
xarray/write/load machinery -- this is a standalone measurement of the
object-model layer only, not a drop-in replacement. `Ncf` is stubbed
(`NcfProto`) rather than importing the real attrs-based `Ncf`, since
mixing attrs and pydantic components isn't the point of this exercise.
`Component`'s full `MutableMapping` interface is intentionally out of
scope here too (see the plan doc) -- this only exercises the single-child
("only") case via `ncf`.

Run directly: `python docs/dev/prototypes/pydantic_dis_prototype.py`
"""

from __future__ import annotations

from abc import ABC
from typing import Annotated, Any, ClassVar, Optional

import numpy as np
from numpy.typing import NDArray
from pydantic import ConfigDict, Field, ValidationInfo, field_validator
from pydantic.dataclasses import dataclass

# Applied to every class in the hierarchy explicitly (dataclass config
# isn't inherited across `@dataclass`-decorated subclasses the way
# BaseModel's `model_config` is) -- one constant, repeated per class, same
# shape codegen already has today (`@attrs.define(kw_only=True,
# slots=False)` emitted on every generated class).
_CFG = ConfigDict(
    arbitrary_types_allowed=True,  # for np.ndarray / NDArray fields
    validate_assignment=True,
    extra="forbid",  # required for Field(init=False) to actually bite -- see module docstring
)

_DTYPE_MAP = {"integer": np.int64, "double": np.float64}


# ============================================================================
# Component: parent/child wiring + dimension resolution
#
# FRICTION POINT #1: attrs' private-attribute convention (`_parent` field,
# `parent=` constructor kwarg, via leading-underscore name mangling)
# doesn't exist in pydantic -- and doesn't need to. A field just named
# `parent` works directly. `exclude=True` is inert at runtime here (a
# dataclass has no built-in dump method to honor it -- see the plan doc's
# BaseModel-vs-dataclass section) but documents intent for if/when a
# `TypeAdapter(cls).dump_python(...)` call is ever added; flopy4 already
# does its own field-filtering in `to_dict()` regardless (its
# `attrs.asdict(..., filter=...)` call excludes "parent"/"_parent" by
# name today), so this isn't a functional gap.
# ============================================================================


@dataclass(config=_CFG, kw_only=True)
class ComponentBase(ABC):
    filename: Optional[str] = None
    name: Optional[str] = None
    parent: Optional["ComponentBase"] = Field(default=None, exclude=True, repr=False)
    dims: dict = Field(default_factory=dict, exclude=True)

    # attrs' `attrs.Factory(lambda self: ..., takes_self=True)`
    # (Component.name's real default: the lowercased *runtime* class name)
    # has no direct per-field equivalent here either -- `default_factory`
    # callables take no arguments in pydantic, same as in stdlib
    # dataclasses. Filled in here, in `__post_init__` -- pydantic
    # dataclasses use the same single post-construction hook stdlib
    # dataclasses do (not BaseModel's two-hook `model_validator(mode=
    # "after")` + `model_post_init` split), which turns out to be a
    # *closer* match to attrs' single `__attrs_post_init__` than v2's
    # BaseModel-based version was.
    def __post_init__(self) -> None:
        if self.name is None:
            self.name = type(self).__name__.lower()
        self._set_child_parents()

    def default_filename(self) -> str:
        return f"{self.name}.{type(self).__name__.lower()}"

    # FRICTION POINT #3 (see plan doc): `attrs.fields(cls)` -> a pydantic
    # dataclass's own `__pydantic_fields__` (or, more portably,
    # `dataclasses.fields(cls)` combined with each field's pydantic
    # `Field(...)` extras) -- same shape as BaseModel's `model_fields`,
    # just a different attribute name. `.metadata` dict ->
    # `Field(json_schema_extra={...})`, unchanged from v2.
    @classmethod
    def _pydantic_fields(cls) -> dict[str, Any]:
        return cls.__pydantic_fields__  # type: ignore[attr-defined]

    @classmethod
    def _child_fields(cls) -> list[str]:
        """Fields whose annotation is (or wraps) another ComponentBase --
        replaces attrs_xarray.child_field_candidates() for the "only" case
        this prototype needs (Dis -> Ncf)."""
        names = []
        for fname, finfo in cls._pydantic_fields().items():
            ann = finfo.annotation
            args = getattr(ann, "__args__", ())
            candidates = (ann, *args)
            if any(isinstance(a, type) and issubclass(a, ComponentBase) for a in candidates):
                names.append(fname)
        return names

    def _set_child_parents(self) -> None:
        for fname in self._child_fields():
            child = getattr(self, fname, None)
            if isinstance(child, ComponentBase):
                object.__setattr__(child, "parent", self)
                if child.name is None:
                    object.__setattr__(child, "name", fname)

    # -- DimensionResolverMixin equivalent --------------------------------
    def get_dims(self) -> dict[str, int]:
        return {}

    def resolve_dims(self, *dims: str) -> dict[str, int]:
        if "_dimension_cache" not in self.__dict__:
            self.__dict__["_dimension_cache"] = {}
        cache = self.__dict__["_dimension_cache"]

        all_dims: dict[str, int] = {}
        if self.parent is not None:
            all_dims.update(self.parent.resolve_dims())
        all_dims.update(self.get_dims())
        for fname in self._child_fields():
            child = getattr(self, fname, None)
            if isinstance(child, ComponentBase):
                all_dims.update(child.get_dims())
        cache.update(all_dims)

        if not dims:
            return all_dims
        return {d: all_dims[d] for d in dims if d in all_dims}


# ============================================================================
# Package: griddata broadcasting via a single, generic field_validator
# ============================================================================


@dataclass(config=_CFG, kw_only=True)
class PackageBase(ComponentBase, ABC):
    # FRICTION POINT #5: a griddata field's *declared* type is
    # `NDArray[np.float64]`, but its *default value* in the current attrs
    # code is a bare scalar (`default=1.0`) that only becomes a real array
    # once dims are known. attrs never type-checks this mismatch. Pydantic
    # DOES enforce it (confirmed by running this prototype): constructing
    # `DisProto(delr=100.0, ...)` raises `ValidationError: Input should be
    # an instance of ndarray` without a coercion step.
    #
    # This does NOT need to be written once per field, or once per
    # generated class -- a single `field_validator("*", mode="before")`,
    # defined ONE time on this shared base, driven by each field's own
    # `json_schema_extra["shape"]` metadata (the metadata `spec.py`'s
    # `field()` helper already emits today), covers every array field on
    # every subclass, including under `validate_assignment=True`
    # (confirmed: assigning `d.delr = 5.0` after construction still
    # coerces). Codegen's array-field template doesn't need to emit a
    # validator at all -- just the `shape=` metadata it already writes.
    @field_validator("*", mode="before")
    @classmethod
    def _coerce_arrays(cls, v: Any, info: ValidationInfo) -> Any:
        finfo = cls._pydantic_fields().get(info.field_name)
        if finfo is None or v is None:
            return v
        meta = finfo.json_schema_extra or {}
        if not (isinstance(meta, dict) and meta.get("block") == "griddata" and meta.get("shape")):
            return v
        if isinstance(v, np.ndarray):
            return v
        dtype = _DTYPE_MAP.get(meta.get("dfn_type", "double"), np.float64)
        return np.asarray(v, dtype=dtype)

    # Deliberately a plain method, not a validator -- called explicitly
    # from `__post_init__` (see DisProto below), the same way the real
    # `Package._broadcast_griddata`/`DisBase._coerce_griddata` are plain
    # methods called explicitly from `__attrs_post_init__`.
    def _broadcast_griddata(self) -> None:
        dims = self.resolve_dims()
        if not dims:
            return
        for fname, finfo in type(self)._pydantic_fields().items():
            meta = finfo.json_schema_extra or {}
            if meta.get("block") != "griddata":
                continue
            shape_dims = meta.get("shape")
            if not shape_dims:
                continue
            val = getattr(self, fname, None)
            if val is None:
                continue
            try:
                shape = tuple(dims[d] for d in shape_dims)
            except KeyError:
                continue
            dtype = _DTYPE_MAP.get(meta.get("dfn_type", "double"), np.float64)
            if not isinstance(val, np.ndarray) or val.shape == shape:
                continue
            if val.size == 1:
                # scalar (post-_coerce_arrays, a 0-d ndarray) -> broadcast
                object.__setattr__(self, fname, np.full(shape, val.item(), dtype=dtype))
            elif meta.get("layered") and val.size == dims.get("nlay", 1):
                object.__setattr__(
                    self, fname, np.repeat(val, np.prod(shape) // val.size).astype(dtype)
                )
            else:
                try:
                    object.__setattr__(self, fname, val.reshape(shape))
                except ValueError:
                    pass

    def __post_init__(self) -> None:
        self._broadcast_griddata()
        super().__post_init__()


# ============================================================================
# NcfProto: minimal child-component stub (real Ncf is attrs-based and out
# of scope -- this exists only to exercise Component's child-wiring path)
# ============================================================================


@dataclass(config=_CFG, kw_only=True)
class NcfProto(ComponentBase):
    dfn_name: ClassVar[str] = "utl-ncf"
    latitude: Optional[str] = None
    longitude: Optional[str] = None


# ============================================================================
# DisBase / Dis
# ============================================================================


@dataclass(config=_CFG, kw_only=True)
class DisBaseProto(PackageBase, ABC):
    # FRICTION POINT #2, RESOLVED by using a pydantic dataclass instead of
    # BaseModel: these were `attrs.field(init=False)` in the real code --
    # excluded from the constructor entirely, always computed, with attrs
    # raising `TypeError: unexpected keyword argument` if a caller passes
    # one anyway. `Field(init=False)` on a `BaseModel` is silently inert
    # at runtime (confirmed by testing: `M(nodes=999)` just sets
    # `nodes=999`, no error, even under `extra="forbid"`). The identical
    # `Field(init=False)`, on a pydantic dataclass, with `extra="forbid"`
    # in config (see `_CFG` above), DOES work: `DisProto(nodes=999)`
    # raises `ValidationError: Unexpected keyword argument` -- see the
    # demo below. This was the single largest unresolved gap v2 of this
    # prototype (BaseModel-based) found; switching the base to
    # `pydantic.dataclasses.dataclass` closes it entirely, at zero extra
    # code cost (same `Field(init=False)` call either way).
    nlay: Optional[int] = Field(default=None, init=False)
    nrow: Optional[int] = Field(default=None, init=False)
    ncol: Optional[int] = Field(default=None, init=False)
    ncpl: Optional[int] = Field(default=None, init=False)
    nvert: Optional[int] = Field(default=None, init=False)
    nodes: Optional[int] = Field(default=None, init=False)


@dataclass(config=_CFG, kw_only=True)
class DisProto(DisBaseProto):
    dfn_name: ClassVar[str] = "gwf-dis"

    length_units: Optional[str] = Field(default=None, json_schema_extra={"block": "options"})
    nogrb: bool = Field(default=False, json_schema_extra={"block": "options"})
    xorigin: float = Field(default=0.0, json_schema_extra={"block": "options"})
    yorigin: float = Field(default=0.0, json_schema_extra={"block": "options"})
    export_array_netcdf: bool = Field(default=False, json_schema_extra={"block": "options"})
    ncf: Optional[NcfProto] = None

    # Redeclares DisBaseProto's init=False nlay/nrow/ncol as real (init=True)
    # fields, matching the real attrs Dis exactly: DisBase declares all six
    # derived fields init=False, but Dis's own field() redeclaration of
    # nlay/nrow/ncol (real constructor args, `block="dimensions"`) shadows
    # DisBase's -- only ncpl/nvert/nodes stay init=False, computed purely
    # from these three. Pydantic dataclass subclassing honors the same
    # override-by-redeclaration rule attrs does.
    nlay: int = Field(default=1, json_schema_extra={"block": "dimensions"})  # type: ignore[assignment]
    ncol: int = Field(default=2, json_schema_extra={"block": "dimensions"})  # type: ignore[assignment]
    nrow: int = Field(default=2, json_schema_extra={"block": "dimensions"})  # type: ignore[assignment]

    delr: Annotated[
        NDArray[np.float64],
        Field(json_schema_extra={"block": "griddata", "shape": ("ncol",), "netcdf": True}),
    ] = 1.0  # type: ignore[assignment]
    delc: Annotated[
        NDArray[np.float64],
        Field(json_schema_extra={"block": "griddata", "shape": ("nrow",), "netcdf": True}),
    ] = 1.0  # type: ignore[assignment]
    top: Annotated[
        NDArray[np.float64],
        Field(json_schema_extra={"block": "griddata", "shape": ("ncpl",), "netcdf": True}),
    ] = 1.0  # type: ignore[assignment]
    botm: Annotated[
        NDArray[np.float64],
        Field(
            json_schema_extra={
                "block": "griddata",
                "shape": ("nodes",),
                "layered": True,
                "netcdf": True,
            }
        ),
    ] = 0.0  # type: ignore[assignment]

    # No per-field array-coercion validator needed here -- see
    # PackageBase._coerce_arrays above.

    def get_dims(self) -> dict[str, int]:
        return {
            "nlay": self.nlay,
            "nrow": self.nrow,
            "ncol": self.ncol,
            "nodes": self.nlay * self.nrow * self.ncol,
            "ncpl": self.nrow * self.ncol,
        }

    # `nodes`/`ncpl`/`nvert` must exist before `resolve_dims()` (called
    # inside `_broadcast_griddata`) can see them -- same ordering
    # constraint the real `Dis.__attrs_post_init__` documents (compute
    # derived dims, *then* chain to super()).
    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", self.ncol * self.nrow * self.nlay)
        object.__setattr__(self, "ncpl", self.ncol * self.nrow)
        object.__setattr__(self, "nvert", (self.ncol + 1) * (self.nrow + 1))
        self._broadcast_griddata()
        # ComponentBase's own hook (child-wiring/default-name) -- deliberately
        # skips PackageBase.__post_init__ to avoid a second broadcast pass.
        ComponentBase.__post_init__(self)


# ============================================================================
# Demonstration / smoke test
# ============================================================================


def demo() -> None:
    print("=" * 70)
    print("Pydantic Dis prototype v3 (pydantic.dataclasses, current codebase shape)")
    print("=" * 70)

    dis = DisProto(nlay=3, nrow=10, ncol=10, delr=100.0, delc=100.0, top=1.0, botm=0.0)
    print(f"\nget_dims(): {dis.get_dims()}")
    assert dis.nodes == 300 and dis.ncpl == 100 and dis.nvert == 121
    print(f"delr: shape={dis.delr.shape}, dtype={dis.delr.dtype}")
    assert dis.delr.shape == (10,)
    print(f"botm: shape={dis.botm.shape}")
    assert dis.botm.shape == (300,)

    ncf = NcfProto(latitude="lat", longitude="lon")
    dis2 = DisProto(ncf=ncf)
    assert dis2.ncf is not None and dis2.ncf.parent is dis2
    print(f"\nchild wiring: dis2.ncf.parent is dis2 -> {dis2.ncf.parent is dis2}")
    print(f"child wiring: dis2.ncf.name -> {dis2.ncf.name!r}")

    print("\nvalidate_assignment=True in effect:")
    try:
        dis.xorigin = "not a float"
        raise AssertionError("expected a validation error")
    except Exception as e:
        print(f"  dis.xorigin = 'not a float' -> raised {type(e).__name__} as expected")

    print("\nField(init=False) now correctly rejects an explicit kwarg (v2/BaseModel didn't):")
    try:
        DisProto(nodes=999)
        raise AssertionError("expected a validation error")
    except Exception as e:
        print(f"  DisProto(nodes=999) -> raised {type(e).__name__} as expected")

    print("\nAll assertions passed.")


if __name__ == "__main__":
    demo()
