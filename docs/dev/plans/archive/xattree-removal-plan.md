# xattree removal plan

**Status: done.** Merged into `develop` via `67d0922` ("drop xattree
(#356)", 2026-09-16). See [`plan.md`](plan.md)'s "Track B: closed out" for the
current summary; this file keeps the original design record below for
anyone who needs the reasoning behind a non-obvious piece of the current
code shape.

## Background

Two migration tracks touched the same files without being coordinated:
Track A ([`mf6-object-model-plan.md`](mf6-object-model-plan.md)) was migrating the DFN-schema input
to codegen and generalizing namefile structuring/binding resolution;
Track B (this doc, continuing [`protocols-plan.md`](protocols-plan.md)'s numbering) was
migrating the runtime object model off the `@xattree` decorator
(`xattree#36`/`pyphoenix-project#167`) onto plain `attrs` + explicit
protocols/mixins. This document sequenced Track B into sub-phases
3a-3e and choreographed them against Track A so the two didn't
destabilize each other's shared files (`flopy4/spec.py`,
`structure.py`/`unstructure.py`, `mf6/adapters.py`).

Key early finding: `flopy4/mf6/spec.py` already split field decorators
into two families — `xattree_field()`/`xattree_dim()`/... (real
`@xattree`-decorated classes: `Component`, `Context`, `Package`, and
their concrete containers) vs. `field()`/`path()`/`dim()`/`coord()`/
`array()` (codegen-v2 leaf packages, plain attrs, no `"xattree"`
metadata key at all). That meant Phase 3a's actual scope was much
smaller than it looked — only ~10 files still used the xattree-native
decorators, and the `dim()`/`coord()`/`array()` xattree variants were
already dead code (zero call sites).

## Final status

All five phases landed:

- **3a** (unify remaining xattree-native fields onto `field()`/`path()`)
  — most fields moved directly; the last group (`Component`-typed child
  fields, and three `netcdf_*` path fields gated on `unstructure.py`'s
  read path) stayed blocked until 3c/3d supplied a replacement, then
  moved in the final cutover.
- **3b** (`flopy4/protocols.py`, `flopy4/attrs_xarray.py` — ended up
  named differently than this doc's original `flopy4/xarray.py` —,
  `flopy4/mixins.py`) — additive, built and tested independent of the
  rest of the object model.
- **3c** (swap `component.py`/`context.py`/`mf6/adapters.py`/
  `structure.py`/`unstructure.py` onto the new conversion layer) —
  landed once Track A's structuring rewrite stabilized, as planned.
- **3d** (replace parent/child binding) — landed as an in-house
  implementation directly in `flopy4/mf6/component.py`
  (`_resolve_child_name`/`_attach_to_parent_field`/
  `_set_child_parents`), **not** by waiting on the upstream xattree
  naming-consolidation fix this doc had originally gated step 2-4 on
  (see [`xattree-child-naming-plan.md`](xattree-child-naming-plan.md), now superseded for the same
  reason). `Component.pname` — the workaround this phase was meant to
  make obsolete — is deleted.
- **3e** (remove the decorator) — `@xattree` → `@attrs.define
  (kw_only=True, slots=False)` on all 13 decorated classes in one
  cutover, `xattree` dependency dropped from `pyproject.toml`/
  `pixi.lock`.

Along the way, several real (not xattree-specific) bugs were found and
fixed: an infinite-recursion cycle in the new `attrs_to_datatree()` on
back-reference fields; `Package.__attrs_post_init__` never chaining to
`Component.__attrs_post_init__` via `super()` (an ordering bug, not a
missing call); and a shape-tagged array field that hadn't been coerced
to a real ndarray yet being silently dropped instead of treated as array
data. Full suite green throughout (908 passed as of the final cutover).

A follow-up pass the same day (2026-09-16) removed two dead functions in
`flopy4/mf6/spec.py` (`get_field_type`/`to_field`, which read a
`"xattree"` metadata key nothing sets anymore) and every remaining
loose "xattree" comment/docstring reference across source, tests, and
docs — cosmetic cleanup with no behavior change, verified against the
full suite.
