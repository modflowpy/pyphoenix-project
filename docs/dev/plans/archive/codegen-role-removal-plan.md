# Remove the codegen "role" layer

Status: proposal. Separate from the `count=` -> `shape=` refactor
(`count-to-shape-plan.md`), which only merges the three inline-array roles.
Re-check `origin/develop` before starting; codegen files move fast.

## Background

`make.py` (`_build_item_schema`, ~L180-300) classifies each column of an `Item`
row and stores the result as `entry["role"]`, a string. `filters.py` (~L718-860)
then branches on it in `_py_type`, `_is_optional`, `_field_meta` and
`_field_line`. A few other places in `make.py` read it too (~L905-918, ~L1599).

Nothing outside `flopy4/mf6/utils/codegen/` reads `role` or the schema dict
(checked with `git grep` on `flopy4/`, excluding codegen). It is an
intermediate representation between two codegen stages, not runtime metadata.

## Why remove it

- Every role is derived from facts already on the column spec: `isinstance(f,
  File)`, `col.is_cellid`, `col.is_index`, `col.is_row_keyword`, `shape`,
  `col.name == "boundname"`. The string re-encodes them.
- Adding a column kind means editing the classifier in `make.py` and every
  `role` branch in `filters.py`; the two must agree on role names.
- Roles bundle several output decisions (type, optionality, metadata, field
  line). The same bundle is decided in four functions that must stay in sync.
- Several role checks are scattered as `col["role"] in (...)` tuples, which are
  easy to leave out of date (`_is_optional` and `_py_type` list overlapping
  but different sets).

## Target

Render from the column spec directly. One function per column kind returns the
whole rendering (annotation, optionality, metadata, field line) in one place,
so a kind's output decisions live together instead of across four functions.

Suggested shape: a small dataclass (e.g. `RenderedColumn`: `annotation`,
`optional`, `meta`, `line`) built by a per-kind function chosen by a single
dispatcher. The dispatcher is the only place that inspects the column spec.

## Steps

1. Inventory every use of `role`: classifier (`make.py`), the four `filters.py`
   functions, and the other `make.py` reads. List, per role, the output
   decisions it implies.
2. Write a characterization test first: render every Item schema from the
   current DFNs and snapshot the generated source. The cleanup must leave this
   byte-identical.
3. Add the per-kind rendering functions and dispatcher; keep `role` populated
   while the callers move over, one role at a time, running the snapshot after
   each.
4. Remove the `role` key, the string tuples, and the classifier branches that
   only existed to set it.
5. Regenerate and confirm no diff in `flopy4/mf6/` generated files; run the
   full suite and the codegen tests.

## Risks

- Generated output drift. The snapshot test in step 2 is the guard; do not
  skip it.
- `develop` conflicts: `filters.py`/`make.py` are edited by most codegen PRs.
  Land this quickly once started, and keep it behavior-neutral.
- Non-Item code paths (e.g. keystring arms, `nested_union`) have their own
  special cases that may not fit the dataclass cleanly. Decide per case whether
  to fold them in or leave them for later.

## Out of scope

- Changing generated output.
- The `count=` -> `shape=` change (separate plan; it merges only the
  `sized`/`counted`/`array` roles and should land first).
