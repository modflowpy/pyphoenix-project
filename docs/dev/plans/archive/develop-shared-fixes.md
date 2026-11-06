# Shared fixes: `pydantic-plan` → `develop`

**Archived 2026-10-19.** Obsolete: the fixes are on develop or no longer apply. Equality is numpy-aware (`ARRAY_EQ`, `_types.py`), `Component.filename` is a `Path`, `sdd.md` no longer mentions cattrs, and `disbase.py` and the scalar TDIS fields are gone. pydantic-plan itself is stale (draft #367).

Last checked: 2026-09-29, against `origin/develop` at `840b952` and
`origin/pydantic-plan` at `c4178c8` (CI green).

## Background

`develop` (attrs) and `pydantic-plan` (pydantic dataclasses) are kept
side by side as two versions of the MF6 object model, so the two approaches can be
compared. The goal is for them to differ **only** in the object-model
choice. Porting the pydantic migration turned up several bugs that have nothing to do
with pydantic. They also affect `develop`, and this file lists them.

Branch off `develop` and port each fix in the attrs style. Use
`pydantic-plan` as the reference implementation, but don't copy
pydantic-specific code (`Field`, `field_validator`, `__pydantic_fields__`,
`field_meta`, ...). The attrs equivalents are `attrs.field(converter=...)`,
`attrs.fields()`, `f.metadata` and `f.type`.

To read reference code without switching branches:
`git show origin/pydantic-plan:<path>`, or `git show <commit>` for the
commits named below.

## Ground rules

- **Environment:** run everything as `pixi run -e dev ...`. Never use
  `uv run`: it re-syncs `.venv` and drops extras.
- **Checks:** verify with `pixi run -e dev smoke`, and run the full suite only
  when asked. CI also runs `ruff check`, `ruff format --check`,
  `mypy flopy4` and `codespell`, so run those too.
- **Worktrees:** put them under `~/dev/`, never `/tmp`.
- **GitHub:** don't open PRs, issues or comments unless explicitly asked.
- **Commits:** one commit per item is ideal. Every commit made by an
  agent ends with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Re-check first:** `develop` moves fast (#371–#373 landed after this
  list was first written and fixed part of item 1). Re-check each item
  against current `develop` before starting it, then update this file:
  remove an item once it's ported.

## Suggested order

| # | Item | Size | Why this position |
|---|------|------|-------------------|
| 1 | Griddata dtype in `_coerce_griddata` | tiny | one line plus a test; isolated |
| 2 | Tdis array defaults | small | isolated to `tdis.py` |
| 3 | `sdd.md` cattrs references | small | docs only |
| 4 | Remaining input-parsing gaps | small | two isolated spots |
| 5 | `filename` as `Path`, POSIX paths | medium | touches the writer, converter and tests; widest reach |
| 6 | Array-aware equality | medium | needs a design decision; do it the same way on both branches |

---

## 1. `_coerce_griddata` casts all griddata to float64

- **Where:** `flopy4/mf6/gwf/disbase.py:45`
  ```python
  dtype = _PKG_DTYPE_MAP.get(f.metadata.get("dfn_type", "double"), np.float64)
  ```
  Nothing sets a `dfn_type` key in field metadata, so this always
  resolves to float64.
- **Symptom:** on `pydantic-plan`, a layered `idomain=1` was repeated per
  layer and `.astype(float64)`'d. It was then written as
  `CONSTANT 1.00000000e+00`, and the macOS mf6 build rejects that for an
  integer array. This made `test_gwf_chd01` and
  `test_gwf_oc_period_variations` fail on macOS. The Linux and Windows builds
  accept it.
- **On develop:** latent, because scalars are expanded earlier so this
  branch isn't hit in the same way. It's the same dead lookup, though.
- **Fix** (reference: `c4178c8`): resolve the dtype the way `Package`
  does.
  ```python
  from flopy4.mf6.spec import to_field_type
  dtype = _PKG_DTYPE_MAP.get(to_field_type(f.type), np.float64)
  ```
- **Test:** port `test_layered_int_griddata_keeps_int_dtype` from
  `pydantic-plan:test/mf6/test_mf6_component.py`. It builds
  `Dis(nlay=2, nrow=1, ncol=3, top=1.0, botm=[0.0, -1.0], idomain=1)` and
  asserts `dis.idomain.dtype == np.int64`.

## 2. `Tdis.perlen`, `nstp` and `tsmult` default to bare scalars

- **Where:** `flopy4/mf6/tdis.py:32-34`. The fields are typed `NDArray[...]`,
  but the defaults are `1.0`, `1` and `1.0`, so `__attrs_post_init__` has to
  branch on scalar vs. array.
- **Reference:** `origin/pydantic-plan:flopy4/mf6/tdis.py`, lines 49–51 and
  84–98.
  - The defaults are 0-d arrays created by a factory (e.g.
    `np.array(1, dtype=np.int64)`).
  - A converter runs `np.asarray` on any explicit value.
  - Post-init checks `.size == 1` and broadcasts to `nper` with `np.full`.
    Otherwise it casts to the declared dtype.
- **On attrs:**
  `attrs.field(factory=lambda: np.array(1.0), converter=np.asarray)` or
  similar. Keep the `perioddata` path working.
- **Tests:** existing Tdis and `Time` tests should keep passing. Add one
  asserting that the default `Tdis()` fields are arrays of length `nper`
  with the right dtypes.

## 3. `docs/dev/sdd.md` still describes cattrs

- **Where:** lines 146, 159, 161 and 170 say the conversion layer uses
  `cattrs` converters with structuring and unstructuring hooks. Neither branch
  uses cattrs.
- **Fix:** describe the actual converter. That's
  `flopy4/mf6/converter/ingress/structure.py` (`structure_component`) and
  `flopy4/mf6/converter/egress/unstructure.py`.
  `origin/pydantic-plan:docs/dev/sdd.md` has a reworded version to start
  from, but develop's wording should say attrs.

## 4. Remaining input-parsing gaps

pydantic's validation exposed these while loading the real MF6 input
corpus. attrs doesn't validate, so on `develop` they store the wrong type
without an error.

**Already fixed on develop:** #373 (`840b952`) fixed keyword rows with a
trailing modifier (`NEWTON UNDER_RELAXATION`), a single `AUXILIARY` name, and
stale extra tokens on scalar options (IMS `OUTER_MAXIMUM 100 500`). It
picks the value from the field's type in `structure.py:~733`. The
`Npf.rewet` Record routing was already on develop too.

Still to port:

| Case | develop stores | Fix | Reference |
|---|---|---|---|
| `START_DATE_TIME 1970-01-01T00:00:00` | a token list, because the numeric grammar splits the leading digits off before the first `-`: `[1970, "-01-01T00:00:00"]` | the converter joins a list into one string | `pydantic-plan:flopy4/mf6/tdis.py:26-47` |
| `START_DATE_TIME 1997` (a bare year) | an `int` in an `Optional[str]` field | the same converter does `str()` on an int or float | same |
| Missing optional period column (e.g. `boundname`) | `NaN` (a float) in a str field, from pandas | drop `pd.isna(v)` values before `item_cls(**row)` so the default applies | `pydantic-plan:flopy4/mf6/package.py:383-388`; develop spot is `package.py:318` |

Check first whether #373's grammar change for trailing text affects the
`START_DATE_TIME` tokenization.

**Tests:** add unit tests that load a small input with each case and check
the stored type (e.g. `isinstance(tdis.start_date_time, str)`).

## 5. `Component.filename` as a `Path`, with POSIX separators in written files

- **Where:** `flopy4/mf6/component.py:153` has `filename: str | None`. develop's
  own `docs/examples/frenchman-flat.py:706` already assigns a `Path` to
  it.
- **Why:**
  - `filename` is a path relative to the workspace, and namefile FNAMEs can
    include subdirectories.
  - The DFN file-record fields are already `Path`, so this makes them
    consistent.
  - Writing `as_posix()` makes input files portable across platforms,
    since MF6 accepts `/` on Windows.
- **Reference:** `c900c60` (main change) and `c4178c8` (the Windows test
  fix).
  - **Type:** `filename: Optional[Path]`, with a converter from `str` to
    `Path`, since attrs won't coerce it (pydantic did).
  - **Internal assignments to wrap in `Path(...)`:**
    - `simulation.py`: the `mfsim.nam` check and assignment
    - `converter/ingress/structure.py`: `child.filename = Path(fname)`
    - `converter/__init__.py` and `mf6/__init__.py`: `Path(path.name)`
    - `gwf/disbase.py`: the `ncf.filename.name` path. develop now has
      `Path(Path(ncf.filename).name)`, which simplifies once it's a `Path`.
  - **Calls to `.as_posix()` wherever a path is written:**
    - `converter/egress/binding.py`: `fname=`
    - `converter/egress/unstructure.py`: `_path_to_tuple`
    - `item.py`: the path branch of `to_tokens`
    - `record.py`: `to_tokens`; add a `PurePath` branch
    - `codec/writer/filters.py`: `quote_if_needed(value: Any)` returns
      `value.as_posix()` for a `PurePath`. develop's `filters.py` changed
      in #372, so merge carefully.
    - `codec/writer/templates/macros.jinja`: the `OPEN/CLOSE` line becomes
      `OPEN/CLOSE {{ value|quote_if_needed }}`. That branch can't be reached
      today (`array_how()` never returns `"external"`). **Keep it** and
      route it through the filter.
- **Watch out for:**
  - Tests that compare `filename` to a str. On pydantic-plan,
    `test_to_xarray_on_context` had to expect `Path("mfsim.nam")`.
  - Tests that compare written output to `str(path)`. They fail on Windows.
    Fixed in `test_quickstart_netcdf` and `test_quickstart_netcdf_mesh` by
    comparing to `nc_fpth.as_posix()`.
  - `attrs_xarray.py`: check that a `Path` filename serializes correctly.
- **Tests to port:** `test_filename_is_path` and
  `test_external_array_path_is_posix`, both in
  `pydantic-plan:test/mf6/test_mf6_component.py`.

## 6. Equality breaks on components with array fields (not fixed on either branch)

- **Problem:**
  - attrs' generated `__eq__` compares field tuples, so ndarray fields hit
    numpy's elementwise `==`. The result is an array or
    `ValueError: truth value ... is ambiguous`.
  - On pydantic-plan the generated `__eq__` raises the same way.
  - Any `Dis(...) == Dis(...)` hits this.
- **Needed:** numpy-aware equality.
  - Use `np.array_equal` for ndarrays. Decide about NaN
    (`equal_nan=True`?) and dask arrays (don't compute them implicitly;
    maybe identity or `NotImplemented`).
  - Skip `parent`. On pydantic-plan, `_parent` has `compare=False` and
    `dims` is an `InitVar`; see `test_eq_ignores_dims_and_parent`.
- **Options on attrs:**
  - (a) `eq=False` on the class decorator and a hand-written `__eq__` on
    `Component`.
  - (b) A per-field `eq=attrs.cmp_using(eq=np.array_equal)` on array
    fields. Fields are generated, so this would go in the codegen
    templates (`flopy4/mf6/utils/codegen/`).
- **Gotcha:** a subclass decorated with `@attrs.define` / `eq=True`
  **generates its own `__eq__` and overrides a base-class one**. That's
  exactly how pydantic-plan's hand-written `Component.__eq__` was silently
  dead. Make sure whichever approach you pick actually runs on generated
  subclasses, and test it on a real subclass, not on `Component`.
- **Coordinate with the user before implementing.** This should be done
  the same way on both branches, so it's a design decision, not a
  mechanical port.
- **Tests:** two equal `Dis` instances compare equal; changing one element
  of `idomain` makes them unequal; `parent` doesn't affect the result.

---

## The other direction (develop → pydantic-plan), for context

This isn't part of the task, but `pydantic-plan` will eventually need
develop's recent work merged in:

- **#366:** TAS support, and DFN-driven rules instead of hardcoded ones. This is
  partly done already: pydantic-plan's codegen matches develop apart
  from the decorator.
- **#371:** creates a component's parent directory before writing it.
- **#372:** writes floats losslessly by default (`WriteContext`,
  `filters.py`).
- **#373:** trailing-text support. Its type-driven option parsing is
  cleaner than pydantic-plan's version (which matches `auxiliary` by name
  and branches on `to_field_type`), so pydantic-plan should adopt
  develop's version.

## Not applicable (checked, nothing to port)

- **Loop-variable shadowing in `structure.py`:** `for name, f in ...`
  shadowed `structure_component()`'s `name` parameter. It exists only on
  pydantic-plan, because develop iterates `attrs.fields()` and uses `f.name`.
