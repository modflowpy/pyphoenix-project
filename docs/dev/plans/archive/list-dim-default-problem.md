# Linked dimensions: explicit value vs. default

Deferred from the list shape-bounds follow-up (see
[`codegen-base-class-removal-plan.md`](codegen-base-class-removal-plan.md), "Default rows" and the list-dimension
section; devtools `list-shape-bounds-plan.md`).

## Problem

`Package._set_dim_from_rows` (`flopy4/mf6/package.py`) decides whether the
user gave a linked dimension by comparing its value to `None`, `0` and the
field's attrs default:

```python
declared = getattr(self, dim)
if declared in (None, 0, attrs.fields_dict(type(self))[dim].default):
    object.__setattr__(self, dim, nrows)   # treated as "not given"
```

When the DFN gives the dimension a default, an explicit value equal to that
default looks the same as no value at all. TDIS is the case that exists
today: `nper` defaults to `1` (from the DFN `default_value`), so

```python
Tdis(nper=1, perioddata=[row, row, row])
```

silently becomes `nper=3`. Once exact shapes are enforced, `nper=2` with three
rows raises but `nper=1` with three rows does not. The check is inconsistent
right at the most common value.

The same applies to any linked dimension with a non-`None` default (a DFN
`default_value` on a DIMENSIONS field), and to an explicit `0`. ATS is the
other current case: `maxats` defaults to `1`, so `Ats(maxats=1,
perioddata=[2 rows])` silently becomes `maxats=2` instead of breaking the
`<=maxats` bound.

## Options

1. **Codegen emits `default=None` for linked dimensions** and moves the DFN
   default into metadata (e.g. `dim_default=1`). `_init_item_lists` resolves
   it: rows given → `nrows`, no rows → `dim_default`. `None` then really
   means "not given". Recommended. It's the smallest change and fits how
   `default_rows` already works.
   - Cost: the attrs default is `None` instead of `1`, so anything that reads
     the field's default from the class (docs, introspection) sees `None`.
     `Optional[int]` is already the annotation.
2. **A private sentinel default** (`UNSET`) instead of `None`. Same logic,
   but it keeps `None` free to mean something else. Nothing needs that today.
3. **Record which init args were given** (wrap `__init__` or use an attrs
   hook). This is the most precise, but it's the most machinery and is harder
   to keep working with `evolve`/copying.

## Also to decide

- Is an explicit `0` ever valid for a linked dimension? If not, it should
  probably raise rather than be treated as "not given".
- The dimension is synced only at construction. Adding rows later doesn't
  update it or check it. This is separate, but touches the same code.

## Tests to add

- `Tdis(nper=1, perioddata=[3 rows])` raises (exact shape).
- `Tdis(perioddata=[3 rows])` → `nper == 3`.
- `Tdis()` → `nper == 1`, one default row.
- `Tdis(nper=3)` → three default rows.

## Resolved

Option 1, on `codegen-mixins` (`aafd47b`). `nper`/`maxats` default to `None`
with `dim_default=1` metadata; `Package._dim_value` applies it only when no
rows are given. An explicit `0` now counts as given (checked like any value).
