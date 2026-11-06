# Spec: array-aware equality for components (item 6)

**Status: implemented and merged as #394 (2026-10-03).** Kept for porting to
`pydantic-plan`; see the Design and `array_eq` sections.

Same design on `develop` (attrs) and `pydantic-plan`. Only the mechanism for
attaching a comparer to a field differs.

## Problem

Generated `__eq__` compares field tuples, so ndarray fields use numpy's
elementwise `==` and raise `ValueError: truth value ... is ambiguous`.
Any `Dis(...) == Dis(...)` fails; `Ims() == Ims()` works.

## Design

Per-field comparers, not a hand-written `Component.__eq__`. The framework's
own generated `__eq__` stays in charge, so a subclass decorator (`eq=True`)
can't silently shadow a base-class override.

- attrs: `eq=attrs.cmp_using(eq=array_eq)` on array fields.
- pydantic-plan: the equivalent per-field mechanism (to be decided there).
- Applied by default in `spec.field()` (the shared field helper) when the
  annotation is `NDArray[...]`, `IntArrayLike` or `FloatArrayLike`, so
  generated classes and hand-written subclasses using `field()` are covered
  with no template changes. Fields declared with bare `attrs.field()` must opt
  in explicitly.

## `array_eq(a, b)` semantics

1. Shape must match.
2. dtype must match.
3. Values equal, with NaN == NaN at the same position. `equal_nan` applies
   only to float/complex dtypes (`np.isnan` fails on object/str arrays).
4. dask-backed arrays are never computed. Equal only if shape, dtype, chunks
   and the dask graph `name` match (same name means the same computation).
   Otherwise unequal.
5. Mixed dask/numpy: unequal (no implicit compute).

## Fields included

- `parent` is excluded (already `eq=False`).
- `dims` is excluded (already `eq=False` on develop; an `InitVar` on
  pydantic-plan). It is a construction-time hint used to derive array shapes,
  so equal arrays already capture what it determined. This keeps
  `test_eq_ignores_dims_and_parent` valid on both branches.

## Tests (real generated subclass, not `Component`)

- Two equal `Dis` compare equal.
- Changing one element of `idomain` makes them unequal.
- Same values but different dtype or shape: unequal.
- NaNs in the same place: equal.
- `parent` and `dims` do not affect the result.
- Two dask-backed fields: equal when they are the same graph, unequal otherwise,
  and no compute is triggered.
- A subclass decorated with `@attrs.define` still gets array-aware equality
  (guards against the override gotcha).

## Prerequisite (done)

The TDIS change that dropped the separate `perlen`/`nstp`/`tsmult` (#379)
arrays first, so no hand-written array fields remain to opt in.
