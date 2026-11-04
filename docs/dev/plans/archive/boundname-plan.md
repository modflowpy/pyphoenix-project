# Boundnames and token text, end to end

**Archived 2026-10-19.** Done: #470 (boundname fixes) and #478 (boundnames on the `when` mechanism). Step 3 (keep number-like text) is open as item 2 of [`followups.md`](../followups.md); step 4's `begin`/`end` check was dropped.

Plan for one piece of work covering how flopy4 builds, writes and reads
boundnames (and other free-text values like obsnames), so that a value
round-trips the way MF6 itself treats it. Pulls together #459, #465, the
quoting in #462, and the reader bugs found while reviewing #462 and #464.

Checked against develop `e73d059d`, #462 at `3c0a4706` (merged as `0b2bb73d`,
trimmed: no `_RESERVED_PREFIX`/`_LOOKS_LIKE_NUMBER`), #464 at `0c2f451d`,
and MF6 6.7.0 (`~/dev/modflow6/bin/downloaded/mf6`) with hand-written input
files.

## Status (2026-10-15)

Open as #470 ("boundname fixes", supersedes #465), branch `boundname-text`
on the fork at `7069b861`, off develop `e8f2b939`, four commits:

- Step 1: `spec.string(empty_is_none=...)`; the generator sets it on the
  last column when optional, untagged and a string (the 28 generated
  boundnames). The name file's `pname` isn't a generated item, so the
  loader maps `''` to None.
- Step 2: done on develop by #467's row layout (presence from the
  `boundnames` option, per [`record-unify.md`](../lists/record-unify.md) rule 4); #470 only trims
  the docstrings it left.
- Step 5: other string fields and files reject `""`; the writer raises on
  an empty value as a backstop.
- Step 6: boundname round-trip tests, including numeric and keyword-like
  names.

Not in #470:

- Step 3 (keep number-like tokens' text). Without it, an obsname `1.50`
  still reloads as `1.5`.
- Step 4's `begin`/`end` check (`tokens2line`), dropped before the PR.

Follow-ups:

- #470 conflicts with `option-columns` (`item.py`, `package.py`,
  `test_mf6_io_roundtrip.py`); rebase whichever merges second.
- After both merge, fold boundnames into the option mechanism
  (`modflow-devtools/when-attribute-plan.md`, flopy4 step 3): boundname
  gets `when="boundnames"` from the DFN, `RowContext.boundnames` becomes
  `"boundnames" in options`, and `Package._coerce_item_list`'s boundname
  branch joins the option loop.

## What MF6 does

Verified by running MF6 on small GHB + OBS models, and in the source
(`BlockParser.f90`, `urword` in `InputOutput.f90`):

- **A row's columns are decided by position, from the package's options.**
  A boundname is whatever comes after the fixed and aux columns. Its text
  can be anything: `5`, `1.50`, `end`, `endpoint` all load.
- **Quotes only group a word.** `urword` returns the text inside the quotes,
  so a quoted word is otherwise treated exactly like a bare one.
- **Only a line's first word can be BEGIN/END.** `end` later in a line is
  data (a boundname `end`, or an OBS id `end`, both work). An obsname `end`
  at the start of a line ends the block, **quoted or not** (`'end'` fails
  the same way).
- **OBS can't refer to a numeric boundname.** An OBS id that looks like a
  number is read as a cell location (`5` -> layer 5), quoted or not. A
  boundname `5a` works.
- `''` as a boundname loads without error.

## What flopy4 does now

Built in Python, written, reloaded with `Simulation.load`, and run through
MF6 (all MF6 runs succeeded):

| Case | develop | #462 |
|---|---|---|
| boundnames `end`, `begin`, `endpoint` | round-trips, written bare | round-trips, written quoted |
| boundnames `5`, `1.50` | **reload as `None`** | written `'5'`, `'1.50'`, **still reload as `None`** |
| boundname `5` with one aux column | **boundname `None`**, aux kept | same |
| obsname `1.50` | **reloads as `1.5`** | written `'1.50'`, round-trips |
| boundname `""` | written as no boundname, reloads `None` | same |
| boundname `None` mixed with named rows | round-trips | same |

## Problems

1. **The reader decides boundname presence by type, not position**
   (`item.py:720-722`, `Item.from_tokens`). A trailing token is taken as a
   boundname only if it's a string that doesn't parse as a number. So a
   numeric boundname is silently dropped, whether or not it was quoted.
   (#462's comment that it also shifts columns doesn't hold: with an aux
   column, the aux value is kept and only the boundname is lost.)
2. **The reader loses the original text of numeric-looking values.** The
   basic transformer turns every number-like token into a number before the
   schema is known, so a string field gets `str(1.5)`: obsname `1.50` comes
   back as `1.5`, which also renames its CSV column. #462's quoting hides
   this for files flopy4 writes, but not for files written elsewhere.
3. **Python-side construction is inconsistent about `""`.** In
   `construct_item`, `((0,0,0), 1.0, "")` gives boundname `None` but
   `((0,0,0), 1.0, (), "")` gives `""` (#465). The writer already treats
   `""` as no boundname (`Item.to_tokens`: `if boundname:`), and MF6 has no
   use for an empty name, so `""` is a third "no boundname" state that can't
   survive a round trip.
4. **The writer quotes things MF6 doesn't need quoted** (#462's
   `_RESERVED_PREFIX` and `_LOOKS_LIKE_NUMBER`), working around problems 1
   and 2 and the typed grammar's begin/end bugs (fixed in #464). It also
   can't help in the one case MF6 can't represent: a `begin`/`end` value at
   the start of a line.

## Plan

1. **Normalize `""` to `None` for trailing optional labels whenever an item
   is built.** Which fields get this comes from the DFNs, not a name list
   (see "Deriving the rule from the DFNs" below): it's boundnames and the
   model name files' `pname`. The rest of this step says "boundname" for
   short.
   This makes `None` the only "no boundname" value. Writing needs no change: it
   already never writes an empty boundname. Put the normalization in a
   converter on the `boundname` field itself, not in `construct_item`:
   user input (tuples, dicts, dataframes) and loading (`from_tokens`) both
   build items through the class, so one converter covers both. That
   matters after #462, where a hand-written `''` boundname (which MF6
   accepts) would otherwise load as `""`. (Need to check that the field
   helper accepts a converter.) Supersedes #465.
2. **Read boundname presence from position.** When the row's widths are
   known (aux count from `sizes`, no optional columns whose presence is
   inferred from the token count), a boundname is there if and only if a
   token is left over. Keep the type check only as a tiebreaker for rows
   that are truly ambiguous, i.e. when an inferred optional group and a
   boundname would use the same token. Even then, the options that gate
   that group (MF6 decides from them) are the better source where we have
   them.
   **Superseded by [`record-unify.md`](../lists/record-unify.md), step 4, rule 4** (agreed
   2026-10-14): presence comes from the `boundnames` option (or, for Python
   input with the option unset, from one surplus value, which sets it), so
   no type-check tiebreaker is needed. Whichever lands first should do it
   the way that rule says.
3. **Keep the original text of number-like tokens**, so a string field gets
   exactly what was in the file. Smallest change: have the basic
   transformer return number subclasses that carry the source text (e.g. a
   `float`/`int` subclass with `.text`), and have string fields and the
   boundname take `.text`. The alternative, keeping all tokens as strings
   until the schema is known, is cleaner but touches far more code.
4. **Writer: quote only for grouping, and raise on what MF6 can't
   represent.** `quote_if_needed` quotes only to keep a value one word
   (#462's `_BARE_WORD` rule). Raise for a `begin`/`end` value that would
   start a line (an obsname), since MF6 rejects it quoted or not, and keep
   #462's error for values containing both quote types. (#462 merged
   without `_RESERVED_PREFIX`/`_LOOKS_LIKE_NUMBER`, so there's nothing to
   remove.)
5. **Reject empty strings in other free-text fields; don't convert them.**
   Outside boundnames, MF6 fails on `''` or does something meaningless
   with it (MF6 6.7.0):

   | Field | MF6 with `''` |
   |---|---|
   | obsname | fails, misleadingly ("Unexpected end of file reached") |
   | OBS id | accepted silently, an observation of nothing useful |
   | `AUXMULTNAME` | fails ("no AUX variable found with this name") |
   | `TS6 FILEIN`, `OBS6 FILEIN` | fails (`Could not open ""`) |

   Required fields have no `None` to convert to, and converting an optional
   option's `""` to `None` would silently drop something the user set,
   usually a bug (e.g. a filename built from an empty variable), which MF6
   would have caught. So add a non-empty validator on free-text string
   fields, applied wherever items/components are built (API and loader
   alike; a file with `''` there is one MF6 rejects anyway). Step 1's
   trailing optional labels (boundname, nam `pname`) are the only
   exception: there `""` naturally means "no label" (e.g. a partly-filled
   dataframe column), and MF6 accepts an absent one. Both rules are derived
   from the DFNs; see below. `quote_if_needed("")`
   then raises instead of writing `''`, as a backstop. During
   implementation, list the DFNs' string fields and confirm none gives an
   empty value a meaning.
6. **Tests.** A round-trip test over the matrix above (build -> write ->
   reload) for each case: boundnames `5`, `1.50`, `end`, `begin`,
   `endpoint`, `""`, `None`, numeric boundname with aux, obsname `1.50`. Plus
   reader tests loading hand-written files (not just flopy4 output), so
   problem 2 is covered for files written elsewhere. If CI has an `mf6`
   binary (the UZF test suggests so), also run the written files through it.

## Deriving the rule from the DFNs

Steps 1 and 5 shouldn't name `boundname`. Classifying every string, file and
string-array field in the v2 spec (devtools `LocalDfnRegistry`,
`~/dev/modflow6-dfns` at `6943c633`, schema `2.0.0.dev3`) shows one
structural class that matches:

**optional, untagged, and the last column of a list row.** Exactly 46
fields, all `boundname` (40) or the model name files' `pname` (6,
`ftype fname pname`, where MF6 picks a default name if it's absent).
Nothing else in the spec, of any type, is in this class.

Why it's principled: a trailing, optional, untagged column is the only kind
of optional column MF6 handles per row by simply leaving it off. Nothing
after it shifts, and no keyword or option controls it, so it's the only
place where empty and absent mean the same thing. Fields that look similar
fall outside it, as they should:

| Field(s) | Why not in the class | Rule |
|---|---|---|
| MVR `mname`, `mname1`, `mname2` | optional and untagged but not last; all present or all absent, controlled by `MODELNAMES` | non-empty |
| OBS id union's `boundname` arm | required, not last; a reference to a boundname, not a label | non-empty |
| tagged optional strings (95, e.g. `AUXMULTNAME`, `CRS`) | follow a keyword; empty means nothing | non-empty |
| SSM `pname` (required), MVR `pname` (key) | required | non-empty |

Implement both rules in code generation: the generator already emits each
field's `optional`/`tagged` metadata, so it can attach the `""` -> `None`
converter to fields in this class and a non-empty validator to every other
free-text string field. Nothing hand-maintained, and new packages pick it
up on sync. (`pname` gains from it too: today an empty `pname` would be
written as `''` under #462, since `to_tokens` only skips `None`.)

## How this relates to the PRs

- **#462 (quoting), merged as `0b2bb73d`.** Landed trimmed: the shared
  `QUOTED` terminal, `unquote`, the merged `quote_if_needed` (`_BARE_WORD`
  rule) and quoting in `record`/`data2lines`. No `_RESERVED_PREFIX` or
  `_LOOKS_LIKE_NUMBER`, so step 4's removal is already done; what's left of
  step 4 is raising on a line-leading `begin`/`end` and on `""`. Without the
  numeric quoting, obsname `1.50` reloads as `1.5` again, as on develop
  before; step 3 fixes it.
- **#464 (begin/end terminals), merged.** Grammar only, no boundname
  code. The `BARE_WORD`/`QUOTED_WORD` rename follows it.
- **#465 (`""` boundname), closed.** Superseded by #470.
- **#459 (merged).** Made a trailing `None` an absent boundname in
  `construct_item`. Step 1 builds on it.

## Sequencing

1. ~~#462~~, ~~#464~~, ~~#467~~, merged.
2. `option-columns` (option-gated columns, the OBS numeric-boundname
   warning, codegen reading the DFN's `when`), then #470 rebased onto it,
   or the other way round.
3. The boundname fold-in, after both.
4. Step 3, if still wanted, as its own PR.

## Open questions

- ~~Should flopy4 warn when an OBS id refers to a numeric boundname?~~ Yes:
  `option-columns` warns.
- ~~Are trailing optional groups and a boundname ambiguous with the options
  known?~~ No: with the package options in `RowContext.options`, columns
  an option turns on are placed by the option (`option-columns`), so no
  type check is needed.
