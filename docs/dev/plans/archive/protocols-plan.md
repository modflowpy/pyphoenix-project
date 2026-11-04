# Dimension Resolution Refactor Plan

**Status: Phases 1-2 (dimension resolution protocols/mixin) shipped
largely as designed below. Everything past that — removing `@xattree`
from `Component`, replacing its parent management, xarray conversion —
was superseded by [`xattree-removal-plan.md`](xattree-removal-plan.md), which sequenced it into
concrete sub-phases and landed all of them (merged `develop`@`67d0922`,
2026-09-16). See [`plan.md`](plan.md)'s "Track B: closed out" for the current
summary.**

## What shipped from this design

`flopy4/mf6/dimensions.py`: `DimensionProvider`/`DimensionResolver`
protocols (renamed from this doc's original `DimensionRegistry`),
`DimensionResolverMixin` (renamed from `DimensionRegistryMixin`), lazy
runtime resolution by walking the object graph on-demand (no
pre-registration, no global state), caching after first resolution,
construction-order-agnostic (supports both top-down and bottom-up
construction). `resolve_dims()` unifies what were originally two
methods (`resolve_dimension()`/`get_all_dimensions()`) into one:
`resolve_dims()` for everything available, `resolve_dims('nlay')` for
one. `Dis`/`Disv`/`Tdis` implement `DimensionProvider` for both explicit
and derived dimensions; `Component` implements `DimensionResolver`, so
every component can register/resolve dimensions uniformly.
`validate_dimension_resolution()` exists as an optional test/CI
validation tool.

This design's own migration section anticipated the parent-management
handoff happening incrementally, with `Component` keeping `@xattree`
"at first." In practice the actual cutover happened all at once in
[`xattree-removal-plan.md`](xattree-removal-plan.md)'s Phase 3d/3e, not incrementally as sketched
here — by the time `dimensions.py`'s `.parent`-walk needed to be
xattree-independent, the whole decorator was being removed in the same
pass rather than swapped underneath it first.

## Original design notes (kept for context)

Lazy resolution order: check cache → walk children for
`DimensionProvider`s → delegate to parent if not found → cache result.
Framework-agnostic by construction (works with attrs, pydantic,
dataclasses) since it depends only on `.metadata`/`.parent`, not a
specific class-decorator mechanism. Conflict detection: eager, raises on
multiple providers declaring the same dimension at one level; children
may still override a parent's dimension of the same name.
