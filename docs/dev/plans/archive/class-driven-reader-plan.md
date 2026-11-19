# Class-driven reader: drop the runtime DFN dependency

**Archived 2026-10-19.** Done: steps 1-3 merged (#455 dropped `flopy4/mf6/dfns/` and the reader's DFN dependency); step 4 deferred as not needed. The devtools items are tracked in that repo.

## Goal

Make the generated classes (and grammars) the only runtime artifacts of
`flopy4 mf6 sync`, so flopy4 doesn't ship `flopy4/mf6/dfns/`, a `__dfn__`
attribute, or read the devtools cache at runtime. As it turned out (see
Steps), the typed reader gets what it needs from the grammars, not the
classes.

Provenance becomes `DFN_COMMIT` (plus the developmode flag, and optionally a
spec digest) in `_contract.py`. mf6 stays the owner of the spec. What flopy4
ships is a generated projection of it, like the `.lark` grammars, never a
hand-edited copy.

## Background

- `flopy4/mf6/dfns/` holds the spec so the typed reader agrees with the
  classes. That fixed the drift from reading the devtools cache at runtime
  (#429), but it ships a copy of the spec and churns about 129 files on
  every develop sync.
- `../modflow-devtools/dfn-cache-for-flopy4-plan.md` proposed making the
  devtools cache fit for runtime use: content-addressed entries, `refs/`
  pointers, `put()` for local checkouts, and so on. If the runtime stops
  needing DFNs, most of that has no consumer. See "devtools" below.
- The writer (`flopy4/mf6/codec/writer`) imports no DFNs. It runs from the
  classes. The reader is the only part that's spec-driven.

## What the reader reads from the DFN today

From `flopy4/mf6/codec/reader/transformer/typed.py` (via
`codec/reader/dfns.py:get_component_dfn`):

- `dfn.blocks`, and `get_fields(recurse=True)` as `_flat_fields` (L29-32)
- block headers (L249-290):
  - record headers (OBS `CONTINUOUS FILEOUT <file> [BINARY]`), using
    `Keyword` vs `File`, `mode_keyword` and `direction`
  - index type (`Double` for `utl-tas` time blocks)
- list element names, and the arms of union items (`_list_elements`, and the
  `ocsetting_all` branch around L326)
- each field's type, used to convert tokens (Keyword → `True`, and so on)
- hyphen vs underscore name matching

## The classes already carry almost all of it

When the type hints are accurate, the annotation plus existing metadata
identifies the DFN type:

| Class side | DFN side |
|---|---|
| `bool` | keyword |
| `int` (`index=True` marks an index) | integer |
| `float` | double |
| `str` | string |
| `Path`, via `path(direction=, keyword=)` | file (`FILEIN`/`FILEOUT` from `direction`; the writer already does this in `item.py:511`) |
| `tuple` + `cellid=` | cellid array |
| `Union[float, str]` + `time_series=True` | time-series double |
| `Union[...]` + `union=("cellid", "index", "string")` | untagged union (OBS `id`/`id2`) |
| arm `Item` classes with `_keyword` and no fields (`Oc.All`, `Oc.First`, ...) | keyword arms of a union |
| `dict[int, ...]` vs `dict[float, ...]` on a block field | block index type (`PERIOD` vs `utl-tas` `TIME`) |
| `_header: ClassVar[str]` on a `Block` (`Obs.ContinuousBlock`) | header record |
| `block=`, `fill_forward=`, `shape=`, `dim=` | block membership, period fill-forward, input dims |

**Principle:** the reader should infer from the classes using the same
conventions the writer uses to emit from them. Format rules live once, in
`Item` / `Record` / `Block` (`Item.from_tokens` already parses union columns
this way). Add metadata to the `field()` / `path()` / `child()` vocabulary
only when the writer needs it too. Don't add any for the reader alone.

## The hints that are wrong

The annotations are only ambiguous in two places. Both are codegen bugs:

1. **Untagged strings are widened to `Union[float, str]`.**
   `codegen/filters.py:850-852`, `value_column`:
   ```python
   object_dtype = object_dtype or time_series
   py_type = "Union[float, str]" if object_dtype else _DFN_PY.get(dfn_type, "float")
   ```
   and `make.py` (around L300) passes `object_dtype=isinstance(f, String)`.
   This confuses the storage dtype (`np.object_` columns) with the type of
   a value. It hits every untagged string column in list items: OBS `obsname`
   and `obstype` (`utl/obs.py`), OC `rtype` (`gwf/oc.py`), and others.
   `boundname` avoids it only because it's special-cased. The line was last
   touched in ee0f593 (#414), and nothing explains the string case.
   **Fix:** plain strings become `str`. Time-series columns stay
   `Union[float, str]`.
2. **Keywords inside records become `Optional[str]` + `tagged=True`.**
   `make.py`, the `col.is_row_keyword` branch:
   `attr_column(name, "str", {"tagged": True}, ...)`. OBS `binary` is the
   example. That looks the same as a tagged string field. Option keywords
   already become `bool`. **Fix:** record keywords become `bool` too.

Expect some fallout from both: item conversion, readers or tests that relied
on the wide hint (numeric-looking obs names, for example), and how the writer
emits record keywords.

## Scope of invertibility

The target is `invert(cls) == normalize(dfn)`, restricted to flopy4's scope:

- **In scope:**
  - I/O structure (everything in the table above);
  - input dims (`shape=`, `dim=`);
  - developmode fields, when codegen runs with `--developmode` (already a
    flag: `make.py:1939`, `dfn2py.py`). Record the flag in `_contract.py`
    and run the check under the same filter.
- **Descriptions** go into docstrings. The DFN text has markup
  (``` ``BINARY'' ```, `\texttt`), so a docstring is a rendered form.
  Compare normalized text, or leave descriptions out of the check. Don't
  parse docstrings back.
- **Out of scope:** the memory section and runtime dims. Those are for
  modflowapi, which should consume the devtools spec directly.
- **Record shapes aren't encoded.** Each reshaping codegen does is a named,
  deterministic rule: filerecord → `child(keyword=...)`, cellid array →
  `cellid=True`, `iper` header → `fill_forward`, `maxbound` → computed
  property. `normalize(Component)` applies the same rules to the DFN side.
  If a rule isn't injective (two DFN shapes collapse into one class form), the
  check fails. Fix it case by case, and only if mf6 reads the two shapes
  differently.

## Steps

Status as of `grammar-driven-reader` (3c7dbe9, 5e5e47c) and
`fix-codegen-hints` (1faebc1):

1. **Fix the hints in codegen.** Done (1faebc1). LAK `bedleak` and MAW
   `head_limit` are `string` in the DFN but hold a number or a word, so
   `str` fields accept numbers for now. See
   `../modflow-devtools/number-or-word-unions-plan.md`.
2. **Make the typed reader DFN-free.** Done, but not as first planned
   (3c7dbe9). The transformer only needed DFN *syntax* (record part names,
   keyword vs value, union arms, record headers, a float block index), and
   the generated grammars already encode that. So every generated rule is
   now named for what it is (`grammar/names.py`), and the transformer reads
   the parse tree alone. `codec/reader/dfns.py` and `dfn_path` are gone.
   The classes don't need to encode record shapes; the grammar keeps them.
   Across the model corpus the output matches the old reader's, apart from
   bugs fixed in the old flat DFN lookup (MAW/LAK/SFR `auxiliary`, union
   arms with hyphens).
3. **Drop `flopy4/mf6/dfns/`.** Done, merged in #455. Sync stops storing
   DFNs and removes the copy earlier syncs left. It also regenerates the
   `.lark` grammars in its staged swap, building each one first and
   removing stale ones.
4. **The `invert(cls) == normalize(dfn)` check.** Deferred, probably not
   needed. With the reader grammar-driven, nothing at runtime relies on the
   classes being invertible, and `structure_component` (already
   class-driven) is covered by the load and round-trip tests. Worth adding
   only if codegen starts losing information those tests can't catch.

Optional later step: if `mf6 --spec` lands upstream, use it to check that the
user's mf6 binary matches the commit the classes came from. The binary
already reports `+<sha>`. This checks compatibility with the installed mf6,
not reader correctness.

## devtools

The devtools cache becomes a **dev-time cache of upstream data**:

- `flopy4 mf6 sync` and codegen read it, run by developers and CI.
- It holds what mf6 publishes (a release's or the nightly's DFN zip), keyed
  by `source@tag`, as in the original DFNs API design.
- Someone who installs a flopy4 wheel never touches it.

So `../modflow-devtools/dfn-cache-for-flopy4-plan.md` shrinks to these items:

- atomic, verified `sync()`:
  - an asset-name template per source in the bootstrap `dfns.toml`
    (`mf{tag}_dfns.zip`);
  - extract into a temp dir under a `FileLock`, reusing the pattern from
    models #364;
  - a manifest file marks an entry as complete;
  - note that `os.replace` onto an existing non-empty directory fails;
- a manifest recording source, tag, asset sha256, the tag's commit (so flopy4
  can drop `_remote_commit`), devtools version and fetch time;
- offline fallback for `latest`, using `cached_tag()` with a warning;
- optionally, `Dfns.digest()`. It must be canonical (`exclude_defaults`,
  sorted keys, fixed JSON separators). It depends on the devtools version,
  because migration runs at load time and `schema_version` doesn't change
  with each migration fix.

Dropped: content-addressed entries, `refs/` pointers, `put()` for local
checkouts, and a `develop` → nightly alias. Use
`modflow6-nightly-build@latest`, or `LocalDfnRegistry` on a checkout when
you need HEAD. A single-file `Dfns.dump` / `load` is nice to have now,
because there's no stored copy to diff.

Upstream asks stay the same: a manifest inside the DFN zip that names the
commit, a published sha256, and later `mf6 --spec`.
