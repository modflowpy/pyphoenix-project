# Simulation.load() corpus gaps

**Archived 2026-10-19.** Done: every cataloged gap is fixed or deliberately skipped (fixture problems). Corpus status now lives in `test/mf6/test_mf6_load_all_models.py` (`KNOWN_PASSING`, `KNOWN_TYPED_GAPS`).

Working doc cataloging the 108 failures `test/mf6/test_mf6_load_all_models.py`
currently `xfail`s (2026-09-11 survey, full 242-model `modflow_devtools`
corpus, after the basic-grammar blank-line fix and the griddata
control-record fix landed — see `git log` on those). Ordered by model count,
each traced to an actual root cause via traceback + source-file inspection,
not guessed from the error string alone. Intent: work through these one at a
time, largest/highest-confidence first, each as its own fix + rerun of the
corpus test to move models from `xfail` into `KNOWN_PASSING`.

## 1. Missing trailing newline at end of file — 34 models — FIXED 2026-09-11

`basic.lark`: made the closing `_NL+` optional (`[_NL+]`) and `start`'s
`(block [_NL*])+` a `*` so end-of-input and a zero-block file both parse.
22/34 cataloged models now pass; the other 12 were misattributed --
their *next* real bug (categories 3, 4, and a new comma-separated-values
variant of 9, e.g. `test059_mvlake_lak_ss`'s `-250,-250,-250,...`) was
masked by this one firing first. Corpus-wide: 134/242 -> 156/242 (55% ->
65%), zero regressions (diffed against the pre-fix probe run). No
remaining work here.

**Symptom**: `UnexpectedToken: Unexpected token Token('$END', '') at line N,
column M` (or similar). One variant is a genuinely empty file (0 blocks) —
`test201_gwtbuy-henryCHD`'s `henry.gwfgwt` is 0 bytes.

**Root cause**: `basic.lark`'s `block` rule requires `_NL+` (at least one
newline) after the closing `"end"i block_name` — but plenty of real fixture
files (confirmed across `test021_twri`, `test006_gwf3`, `test019_VilhelmsenGC`,
several more) simply end right after `END PERIOD`/`END GRIDDATA` with no
trailing newline at all. `_NL+` can't be satisfied by true end-of-input, so
Lark's `$END` pseudo-token shows up where a newline was still expected.
Separately, `start: [_NL*] (block [_NL*])+` requires *at least one* block,
which a genuinely empty file has none of.

**Fix shape**: make the closing `_NL+` optional (`[_NL+]`) so end-of-input
satisfies it same as a real newline would; change `start`'s `(block
[_NL*])+` to `*` to tolerate an empty file with zero blocks. Same family as
the blank-line fix already landed — worth doing together if revisiting
`basic.lark` again. Low risk: verify against the existing reader/namefile
test suites plus a synthetic no-trailing-newline / empty-file case.

**Models**: test001e_UZF_3lay(+TS/_3layTS), test001e_noUZF_3lay,
test001h_evt_array4, test003_gwfs_disv(+_xt3d), test003_gwfs_reduced,
test006_gwf3, test006_gwf3_disv_trimesh(+_xt3d), test006a_gwf3_disv_thickstrt,
test017_Crinkle, test019_VilhelmsenGC, test019_VilhelmsenLGR(+_nr),
test021_twri, test025_ConstantCV(+_perched), test025_VariableCV,
test025_Vertically_Staggered, test041_flowdivert(+_mfusg/_nr/_nwt_dev),
test057_transientchd, test059_mvlake_lak_ss, test104_riv_mvr, test105_ghb_mvr,
test201-205_gwtbuy-henry* (the empty-file variant).

## 2. Multi-line INTERNAL array data truncated to the first line — 29 models — FIXED 2026-09-11

Unified `_read_griddata_control_record` and `_parse_readarray_period_block`'s
duplicated CONSTANT/INTERNAL logic into one shared `_read_control_record`
that takes the array's target length and keeps consuming rows until that
many values are collected (instead of assuming one row), and always
broadcasts CONSTANT to that length itself rather than leaving it to the
caller. Also added the `OPEN/CLOSE` case to `_parse_readarray_period_block`
(it only existed on the griddata side before -- explains why
`test017_Crinkle`/`test019_VilhelmsenGC`(+`LGR`/`_nr`), cataloged under
gap #1's re-attribution as griddata OPEN/CLOSE, were actually hitting
*this* gap instead, in the READARRAY period reader). Verified the fix reads
real data correctly, not just avoids the crash: `test014_NWTP3High`'s 6400
recharge values (spanning 80 lines) cross-checked exactly against the raw
file at both ends. Also spot-checked a previously-passing griddata model
(`test006_gwf3_disv`) to make sure the shared-function refactor didn't
regress the already-correct single-line case.

28/29 originally cataloged models now pass; the 29th
(`test045_lake1tr_dev`) was masking gap #5 (LAK CONNECTIONDATA `HORIZONTAL`
token). Corpus-wide: 156/242 -> 188/242 (65% -> 78%), zero regressions. No
remaining work here.

<details><summary>Original writeup (superseded)</summary>

Multi-line INTERNAL array data truncated to the first line — likely ~29 models

**Symptom**: `ValueError: could not broadcast input array from shape (X,)
into shape (Y,)`, Y a multiple of X (e.g. `(80,)` into `(6400,)`).

**Root cause**: confirmed via `test014_NWTP3High`'s `nwtp3_Rhigh.rch` —
its RECHARGE `INTERNAL` array is written across 80 physical lines (80
values each, 6400 total: an 80×80 grid). `_parse_readarray_period_block`
(READARRAY period path, `structure.py`) reads exactly **one** row after an
`INTERNAL` control record (`data_row = rows[i]; i += 1`) — correct only
when the whole array fits on one physical line. A wrapped array silently
yields just the first line's worth of values, then crashes on the shape
mismatch (direct `accum[fname][kper] = arr` assignment against a
pre-allocated full-shape slot). `_read_griddata_control_record` (the
griddata path) already reads a full data row too, but per-field length
there is bounded by `_griddata_flat_length` + the LAYERED tiling added in
the griddata fix, so it's unclear whether an under-length INTERNAL row
can still silently slip through there — **worth a direct check** before
assuming this category is READARRAY-period-only.

Also confirmed via `test017_Crinkle`/`test019_VilhelmsenGC`(+`LGR`/`_nr`):
`_parse_readarray_period_block` has no `OPEN/CLOSE` case at all (unlike
`_read_griddata_control_record`, which gained one in the griddata fix) —
`ValueError: could not convert string to float: 'OPEN/CLOSE'` at
`structure.py`'s `_parse_readarray_period_block`. Same missing-case bug,
not a length issue.

**Fix shape**: `_parse_readarray_period_block` duplicates
`_read_griddata_control_record`'s CONSTANT/INTERNAL logic almost exactly
(the two were probably written independently) — worth actually unifying
them into one shared control-record reader used by both, picking up
OPEN/CLOSE and multi-line INTERNAL in one place instead of twice. That
reader needs to know the array's expected total length (already
available: `nodes`/`ncpl` for griddata, similarly derivable for READARRAY
period fields) and keep consuming subsequent rows until that many values
are collected, rather than assuming one row. `OPEN/CLOSE`'s file-based
read already isn't affected by the line-wrapping issue (reads the whole
referenced file's `.split()`, regardless of its own internal line
wrapping) — it just needs to exist in both places.

**Models**: not enumerated individually here (29, dominated by
`test014_NWTP3*` and other larger-grid models) — rerun the corpus probe
after the fix and diff against `results_after_fix.jsonl`
(`/tmp/.../scratchpad/results_after_fix.jsonl` this session, won't survive
past it — regenerate via the probe script pattern in this session's
history if needed) to get the exact list.

</details>

## 3. Trailing legacy MODFLOW-2005/NWT content after the last real block — FIXED 2026-09-11

Reconsidered per-user decision 2026-09-11 (originally skipped, revisited
same day): rather than accepting a hard data loss for ~25 models over
content that's genuinely outside the file's own real MF6 blocks,
`codec.reader.loads()` now falls back to trimming anything after the
last recognized `BEGIN...END` block when the file fails to parse as
written -- the trailing content itself is still never interpreted (it
isn't valid MF6 input and nothing tries to make sense of it), only
discarded. Fallback-only by design: a file that already parses cleanly
takes the same path as before, unchanged; the trim only ever engages
after a parse failure, so it can't silently change behavior for the 212
models already passing.

Implementation: `_BLOCK_RE`, a regex matching one well-formed
`^begin <name> ... end <name>$` span (case-insensitive, multiline,
dotall), applied with `re.finditer` to find every such block in the raw
text; truncate to just past the last one found. Deliberately done as
string-level pre-processing before the Lark parse, not as LALR grammar
leniency (recovering from "unexpected trailing input" isn't a natural
fit for LALR, and doing it at the string level keeps the change fully
isolated to this one fallback path).

Verified against real data, not just crash-avoidance: spot-checked
several trimmed models' resulting components before running the full
suite.

Corpus-wide (combined with gap #6's fix below, run together): 212/242
-> 239/242 (88% -> 99%), zero regressions -- the single biggest jump of
any fix this session. 25 of the models originally cataloged under this
gap now pass; none of the trimming logic needed further tuning. No
remaining work here.

## Per-line INTERNAL data annotations (not just the array's last line) — FOUND AND FIXED 2026-09-11, while verifying gap #3

**Symptom**: `ValueError: invalid literal for int() with base 10: 'row'`
-- found on `test004_bcfss`, surfaced only once gap #3's trim let this
model's `.npf` file reach griddata parsing at all.

**Root cause**: `bcf2ss.npf`'s `icelltype`/`k` `INTERNAL` arrays are
written 10 lines (one per grid row), each with a trailing
`  row N` remark:
```
	internal
	0 0 0 0 0 0 0 0 0 0 0 0 0 0 0  row 1
	0 0 0 0 0 0 0 0 0 0 0 0 0 0 0  row 2
	...
```
Gap #10 (see above, in gap #2's writeup) already handled a *single*
trailing annotation on an array's *last* data line via the final
`values[:length]` truncation -- but here every one of the 10 lines
carries its own annotation, including "row" (non-numeric) *and* the row
number itself (numeric, e.g. "1", "2", ... indistinguishable from real
data by value alone). Collecting whole lines and truncating only once
at the very end left annotation tokens from early lines *inside* the
kept range and pushed real data from later lines *out* of it -- silently
wrong before the parser happened to hit the non-numeric word "row" and
raised instead.

**Fix**: `_read_control_record`'s multi-line collection now takes each
line's tokens only up to (not including) its first non-numeric one,
via a new `_numeric_prefix()` helper, rather than the whole line
unconditionally. Correct because real INTERNAL/bare-data-row array
data is always purely numeric -- any non-numeric token marks the start
of an inline annotation for that line specifically, with no need to
know the line's true data width up front. Verified:
`test004_bcfss`'s `icelltype` (300 values, {0,1}) and `k` (300 values,
{5.,10.} -- CONSTANT 10 for layer 1, INTERNAL 5s for layer 2) both
match the file. This is a generalization of the gap-#10 fix, not a
separate one -- same underlying principle (don't trust a control
record's raw token count; trust "numeric" as the boundary of real
data), extended from "only the last line can have a trailing remark"
to "any line can."

### Original writeup (context, superseded)

19 models (+6 more, see below)

Since gap #1's fix, also confirmed for `test003_gwfs_disv`(+`_xt3d`),
`test003_gwfs_reduced`, `test006_gwf3`, `test021_twri`,
`test057_transientchd` — these were previously masked by #1's
missing-trailing-newline symptom firing on some *other* file in the
model first.

**Symptom**: `UnexpectedToken: Unexpected token Token('NUMBER', ...)`,
parser state expects `BEGIN`/`_NL`/`$END` (i.e. it's between blocks,
not mid-block).

**Root cause**: confirmed across `test003_gwfs` (`.dis`/`.ims`) and
`test006_2models` (`model2.npf`) — the file's real MF6 content ends
cleanly at a legitimate `END GRIDDATA`/`END <block>`, but legacy
MODFLOW-2005/NWT-style flat-format content is appended afterward (FORTRAN
format strings like `(10G13.0)`, comment tails like `HK() = Horizontal
hydraulic conductivity of layer 1`) — an apparent `mf5to15` conversion
leftover in these specific `modflow6-testmodels` fixtures, not valid MF6
input.

**Fix shape**: this is arguably not a flopy4 bug — real MF6 itself may or
may not tolerate this trailing content (unverified). Two options: (a) make
`start` lenient about trailing non-block content after the last real block
(stop parsing once no more `BEGIN` is found, ignore the rest) — a real
robustness win but changes what counts as a "valid" file; (b) treat as a
fixture-quality issue out of scope, possibly worth flagging upstream in
`modflow6-testmodels`. Recommend (a) only if it's low-risk to bolt on
without weakening error detection for genuinely malformed files elsewhere
(a trailing garbage block that happens to start with a real `BEGIN` token
would still be entered and fail normally, so this is fairly safe).

**Models**: test003_gwfs(+_obs/_tr), test004_bcfss, test006_2models(+-XT3D/
_gnc/_mvr_dev/_unconf/_unconf_nr/_unconf_nr_gnc/_unconf_tr_nr),
test006_gwf3_gnc(+_nr_mfusg), test006_gwf3_nr_mfusg, test006_gwf3_unconf,
test019_VilhelmsenGF, test106_tsnodata(+/alt_model).

## 4. OPEN/CLOSE for list/period blocks (external file for row data) — 9 models — FIXED 2026-09-11

Added `_resolve_open_close_rows`: detects a block whose only content is a
single `OPEN/CLOSE <fname>` row (period or Pass-2 Item-list blocks),
reads the referenced file, and re-tokenizes its content the same way
inline block content is -- by wrapping it in a synthetic `BEGIN DATA / ...
/ END DATA` and running it back through the existing `loads()` parser,
rather than writing a second, separate tokenizer. Verified against real
data: `test001a_Tharmonic_extlist`'s `chd.txt`-redirected CHD stress
period data (2 rows) loaded and matches the file exactly (cellid,
head, aux all correct, 1-based -> 0-based cellid conversion included).

9 of the 9 confirmed models now pass (the originally-cataloged
`test026_WellReduction` turned out to belong to a different bucket
already fixed by then; `test050_circle_island` is still open, masking
some other bug -- not yet investigated). Corpus-wide: 188/242 -> 197/242
(78% -> 81%), zero regressions. Not handled: any OPEN/CLOSE row option
beyond the bare filename (e.g. a scale factor) -- not seen in the corpus
yet, add if it comes up.

<details><summary>Original writeup (superseded)</summary>

OPEN/CLOSE for list/period blocks (external file for row data) — 11 models

**Symptom**: `ValueError: invalid literal for int() with base 10:
'open/close'` (9 models) or `could not convert string to float: 'open/close'`
/ `'OPEN/CLOSE'` (3 models — overlaps the float bucket below).

**Root cause**: confirmed via `test001a_Tharmonic_extlist`'s
`flow15_constant.chd`:
```
BEGIN Period 1
  open/close chd.txt
END Period
```
A period/list block's row data can be sourced entirely from an external
file, the same `OPEN/CLOSE` keyword as griddata arrays but a *different*
mechanism (the referenced file contains list rows, not a flat numeric
array). `_parse_rows`/`Item.from_tokens` has no concept of this — it feeds
the literal tokens `["open/close", "chd.txt"]` straight into row parsing,
which tries to read `"open/close"` as a numeric column (cellid or similar)
and crashes.

**Fix shape**: in `structure_component`'s Pass 2/3 (block Item-list /
period parsing), detect a block whose *only* content is a single
`open/close <fname>` row, read the referenced file (relative to
`workspace`), and parse its content as this block's rows through the same
path a normal inline block would use. Separate, self-contained feature —
doesn't touch the griddata code from the current fix.

**Models**: test001a_Tharmonic_extlist, test006_gwf3_disv_ext,
test020_mawconfined_openclose, test024_Reilly(+_ext), test026_WellReduction
(needs re-check — appears in both this bucket and elsewhere depending on
which file fails first), test042_lake0_embeddedh_openclose,
test046_periodic_bc_openclose, test050_circle_island,
test051_uzfp2_openclose (some of these overlap with bucket 1/3; re-verify
after fixing this one which ones remain).

</details>

## 5. `infer_ncelldim` miscounts row width for LAK CONNECTIONDATA — 7 models — FIXED 2026-09-11

**Actual root cause** (the earlier `_n_fixed_tokens`-undercounts theory
was wrong -- `_n_fixed_tokens` was already computing the class's real 8
fixed fields correctly): `test045_lake4ss`'s `lakeex4.lak` CONNECTIONDATA
rows carry a 12th trailing token (`... 202.8325 403.7100    2`) with no
counterpart in the *current* `gwf-lak` DFN's `connectiondata` block
(checked the real spec: `ifno iconn cellid claktype bedleak belev telev
connlen connwidth` -- exactly 8 fixed + 3-wide cellid = 11 tokens for a
DIS grid, not 12). This fixture predates a DFN revision that dropped a
field, and `infer_ncelldim`'s row-length heuristic (`total tokens -
fixed - aux - boundname`) has no way to tell "one extra genuinely
unexplained trailing token" apart from "the cellid is one element
wider than expected" -- it always assumes the latter.

**Fix**: grid dimensions (`dims`) already unambiguously say which grid
type is in play (DIS has `nrow`+`ncol` -> ncelldim 3, DISV has `ncpl` -> 2,
DISU has `nodes` only -> 1) -- more reliable than counting tokens, and
already threaded through most of `structure.py`. Added `item.py`'s
`ncelldim_from_dims()`, preferred by `infer_ncelldim()` over the row-length
guess whenever `dims` is available; threaded `dims` down through
`_parse_rows` from `structure_component`'s Pass 2/3 (using the same
`dims or _self_dims_from_kwargs(kwargs)` "effective dims" pattern Pass 4
uses). With the correct ncelldim now given directly rather than guessed,
`Item.from_tokens` consumes exactly the 11 tokens the current class
models and silently drops the unexplained 12th -- same as how MF6's own
list reader tolerates a trailing annotation. Verified against real data:
`test045_lake4ss`'s 110 CONNECTIONDATA rows all parse with correct cellid/
claktype/bedleak/belev/telev/connlen/connwidth, cross-checked against the
raw file's first row by hand.

This is also a strictly more correct general fix, not a LAK-specific
patch -- any package with a variable-width cellid now gets its ncelldim
from the grid instead of guessed row arithmetic whenever `dims` is
available, which should preempt the same failure mode for other
packages/fixtures not yet seen.

7 of the (corrected) 7-model bucket now pass -- confirms the
`_n_fixed_tokens`-undercount theory was never the cause; the 8th model
originally lumped in here (`test016_Keating`, `'NLARRAY'`) was always
gap #6's separate issue. Corpus-wide: 197/242 -> 204/242 (81% -> 84%),
zero regressions. No remaining work here.

## 6. `NLARRAY` field — FIXED 2026-09-11 (reconsidered alongside #3)

`keating.rch` contains *two complete, alternative* RCH package
definitions concatenated -- a plain list-input `BEGIN PERIOD 1` block
(rows like `1 1 180 0.072`, real MF6 syntax) followed by a second,
entirely separate `BEGIN DIMENSIONS` / `BEGIN PERIOD 1` pair using the
READARRAY (`RCHA`-style) convention with a field named `NLARRAY` that
matches no real MF6 DFN field at all. Both halves parse as well-formed
blocks on their own (unlike #3's non-block trailing garbage), so
`BasicTransformer.start()` -- which folds all top-level blocks into one
`{name: rows}` dict -- was building that dict last-write-wins: the
second `DIMENSIONS`/`PERIOD 1` pair silently overwrote the first, so
the whole file effectively became just the broken, `NLARRAY`-based
half.

**Fix**: `start()` now keeps the *first* occurrence of a repeated block
name, skipping later duplicates. Justified narrowly: a block name
repeating within one file is already an anomaly (real MF6 files have at
most one `OPTIONS`/`DIMENSIONS`/etc.; period/solutiongroup blocks are
told apart by their own number, part of the block name itself) -- and
in the one instance found this session, the first occurrence was
unambiguously the intended, real-MF6-syntax one. Verified against real
data: `test016_Keating`'s RCH stress period data (24 rows, cellid
`(0,0,168)`..`(0,0,191)`, `recharge=0.072`) now loads and matches the
file's first (list-format) block exactly.

Corpus-wide (combined with gap #3's fix, run together): 212/242 ->
239/242 (88% -> 99%). No remaining work here.

Models: test016_Keating, test016_Keating_dev.

## 7+8. TIMEARRAYSERIES / per-period AUXILIARY-named array fields not recognized — FIXED 2026-09-11

Confirmed both together via `test027_TimeseriesTest`'s `timeseriestest.rch`
(and separately, `test001h_evt_array3`'s `flow15.evt`):
```
begin options
  ...
  AUXILIARY Auxarray1 RchMult
  AUXMULTNAME RchMult
end options

begin period 1
  RECHARGE  TimeArraySeries  RchSeries
  Auxarray1
    constant  2.3
  RchMult
    open/close  timeseriestest.mltarr  FACTOR  1.0  IPRN  0
end period
```
Two distinct row shapes `_parse_readarray_period_block` didn't recognize:
a field sourced from a named time-array-series (`RECHARGE
TimeArraySeries RchSeries`, a control-record kind of its own, not
CONSTANT/INTERNAL/OPEN-CLOSE) and a per-period array keyed by an
`AUXILIARY`-declared name (`Auxarray1`, `RchMult` -- not a declared class
field at all, since the name is user-chosen). Both desynced the row
cursor the same way: falling through to "bare data row", consuming
whatever row came next (a different field's name) as if it were numeric
data.

**Fix**: `_parse_readarray_period_block` now recognizes a
`TIMEARRAYSERIES`/`TAS6` token anywhere in a field's row and consumes
just that one row, contributing no array data (not resolved to real
values yet -- would need reading and time-interpolating the referenced
`.tas` file, a separate feature). For any row naming a field *not* in
`ra_fields` (declared class fields), it now still consumes that field's
whole control-record block (LAYERED-aware) so the cursor stays aligned
for whatever comes next -- just doesn't store the result, since it's not
resolved to a real array either. Both changes are conservative: neither
crashes, and neither fabricates data that isn't really being read.

Corpus-wide (combined with the fix below): 204/242 -> 211/242, zero
regressions. Data completeness gap remains: TAS-driven and
AUXILIARY-named period arrays load without crashing but aren't
populated (still `FILL_DNODATA`/unset) -- a real, separate feature, not
attempted here.

## delr/delc LAYERED per-record length — FIXED 2026-09-11 (found while investigating #7/#8)

**Symptom**: `ValueError: could not convert string to float: 'delc'`
(or any field-name string) -- a griddata field's own control-record data
run overruns into the *next* field's name row.

**Root cause**: confirmed via `test027_TimeseriesTest_idomain`'s
`timeseriestest.dis`, which (unusually) tags `delr`/`delc` -- true shape
`(ncol,)`/`(nrow,)`, single record, never really "per layer" -- as
`LAYERED` with one `INTERNAL` record each. `_parse_griddata_block`'s
LAYERED branch read each per-record control record using the grid's
per-layer cell count (`ncpl`) unconditionally, correct for genuinely
per-layer fields (`botm`/`idomain`, shape `(nodes,)`) but wrong for a
field like `delr` whose *true* declared length (51, `dims["ncol"]`) is
smaller than `ncpl` (2601 for this 51x51 grid) -- so it kept reading
physical lines (57x more than needed) until it collected 2601 values,
consuming `delc`'s own name row along the way.

**Fix**: per-record read length is now `min(ncpl, target)`, where `target`
is the field's own declared length (`_griddata_flat_length`, already
computed for the post-loop tiling step, just moved earlier). Correct in
both directions: `ncpl` for a truly per-layer field (`target > ncpl`),
`target` itself for a field like `delr` tagged LAYERED despite not truly
being one (`target <= ncpl`). Verified against real data:
`test027_TimeseriesTest_idomain`'s `delr`/`delc` (51 values each, matching
the file), `top` (broadcast to 2601), `botm` (both layer values across
5202 cells) all correct; re-checked four previously-passing griddata
models (`test006_gwf3_disv`, `test001a_Tharmonic`,
`test020_NevilleTonkinTransient`, `test014_NWTP3High`) for no regression.

Also, incidentally, this was gap #10's actual root cause too (see below) --
retroactively fixed by this same change (confirmed, not guessed).

## 9. Comma-separated values with no whitespace — FIXED (both cases) 2026-09-11

**Symptom**: `ValueError: could not convert string to float:
'-250,-250,-250,...'` (test059_mvlake_lak_ss) or `',1,1.00000000'`
(test001a_Tharmonic_tabs).

**Part A -- OPEN/CLOSE-referenced array files**: `test059_mvlake_lak_ss`'s
griddata-referenced `bottom.ref` has comma-separated values with no
spaces at all (`-250,-250,-250,...`) -- `.split()` (whitespace-only)
treated each whole line as one token. `_read_open_close_values` now
replaces commas with spaces before splitting.

**Part B -- inline grammar tokenization**: `test001a_Tharmonic_tabs`'s
`flow15.tdis` writes its `PERIODDATA` row as `1.00000000,1,1.00000000`
-- no OPEN/CLOSE involved, the main grammar's `word` rule tokenized the
whole comma-joined run as one token, since `,` was in its character
class. Excluding `,` alone surfaced a second, unrelated pre-existing
bug: `word`'s class was `[a-zA-Z0-9._'~,+-\(\)]` -- the `-` between `+`
and the escaped `\(` was read by the regex engine as a *range operator*
(`+` to `\`, i.e. 0x2B-0x5C), not a literal hyphen, so `word` actually
matched a much wider set of punctuation (`,-./:;<=>?@[\`) than its four
explicit characters (`.`, `_`, `'`, `~`) suggested -- confirmed by
listing every character the compiled pattern actually matched. Simply
dropping the `,` character (my first attempt) broke
`test011_mflgr_ex3` (a *regression*, caught by the full corpus probe):
its `.wel` file has an inline parenthetical remark --
`(file for binary flow information; must be opened using DATA(BINARY))`
-- containing a `;` that was only ever matched via the accidental wide
range. Fixed properly: rewrote the character class to name the exact
same set explicitly (verified character-by-character against the
original compiled pattern), comma excluded, `-` moved to the end so it's
never a range operator: `[a-zA-Z0-9'().\/:;<=>?@_~+\[\\-]`. A `COMMA`
terminal is `%ignore`d, acting as a token separator like whitespace.

Verified: comma-joined PERIODDATA now splits into 3 numbers matching the
file; the semicolon-containing parenthetical, `open/close` (still one
token, `/` retained), a Windows-style path, and an ISO datetime string
all still tokenize as before. Full reader/loader suite (50 tests) and
the corpus probe (zero regressions after the character-class fix, one
new pass) both confirm.

Corpus-wide: 211/242 -> 212/242, zero regressions (after fixing the
regression the naive first attempt introduced). No remaining work here.

## 10. `TOP LAYERED` with trailing garbage on the INTERNAL data line — CONFIRMED already fixed (retroactively, by the delr/delc fix above)

Re-checked `test001e_UZF_spring` directly: loads correctly now, `top`
values `[10. 10. 10. 10. 6.1 10. 10. 10. 10. 10.]` match the file. The
original theory (genuinely corrupted fixture) was itself wrong -- the
trailing text after the real data (`CONSTANT 10.00000000 TOP array`) sits
on the *same physical line* as the 10 real values, so once the read
length was corrected to the field's true length (10, not `ncpl`), the
existing `values[:length]` truncation already dropped it harmlessly.
No separate fix needed. `test001e_UZF_spring` was already in
`KNOWN_PASSING` as of the delr/delc fix.

## 11. OC `Format` record requires a field the DFN also marks required — investigated, SKIPPED, out of scope (reconsidered, same conclusion)

**Symptom**: `TypeError: Oc.Format.__init__() missing 1 required
positional argument: 'format_'`. Model: test060_gms_ets.

**Investigated**: checked the real `gwf-oc.dfn` directly --
`formatrecord`'s `format` field is declared `tagged false` / `optional
false` (i.e. genuinely required, untagged), matching flopy4's
`Oc.Format.format_` (`attrs.field()`, no default). `ets3_dis.oc`'s
`HEAD PRINT_FORMAT COLUMNS 10 WIDTH 11 DIGITS 4` omits it entirely, so
this fixture doesn't conform to the current spec.

**Re-checked against the precedent that fixed #3/#6** (revisiting a
previously-skipped gap turned out right twice already this session):
`flopy4/mf6/utils/codegen/dfn_overrides.toml` already has an entry
making this *same* `formatrecord`'s `columns`/`width`/`digits`
optional, for a documented reason -- the v1 DFN marks them with a
*bare* `optional` attribute (no value), and the v1->dev3 migration
doesn't handle that form, defaulting it to `false` instead of `true`
([`dev3-migration-gaps.md`](dev3-migration-gaps.md), `devtools/todo.md` 2026-08-18 entry, "30
occurrences across 12 v1 DFN files", 18 of them this `columns`/`width`/
`digits` override). That's a *migration bug* being corrected back to
the v1 DFN's real intent -- not a case of flopy4 overriding a
deliberately-required spec field. Checked whether `format` (the 4th
field in the same `formatrecord`) has the same bare-`optional` v1
pattern: no -- the cached DFN shows `optional false` written out
explicitly, not bare. So this doesn't qualify for the same override
mechanism; `format` really is meant to be required per spec, unlike its
sibling fields. Distinct from #3's "predates a spec change, unverified
either way" framing -- this one's spec status is actually confirmed,
just not in the fixture's favor.

Making `format_` optional anyway would mean flopy4 diverging from a
DFN field the migration got right, purely for one non-conformant
fixture's benefit, and (since `Oc.Format` is autogenerated) would need
a codegen change touching every OC-family package's `formatrecord`
across gwf/gwt/gwe/prt/chf/olf/swf -- a broad blast radius for one
model. Left `xfail`.

## 12. LGR child model's external array file sized for the parent grid — CONFIRMED fixture mismatch, SKIPPED, out of scope

**Symptom**: `ValueError: could not broadcast input array from shape
(26901,) into shape (7020,)`. Models: test019_VilhelmsenLGR,
test019_VilhelmsenLGR_nr.

**Investigated**: this is a Local Grid Refinement (LGR) simulation with a
coarse parent model (`TM9_parent_GN`, 9x61x49 = 26901 nodes) and a fine
child model (`Child_GN`, 25x90x78, ncpl 7020). Confirmed the child's own
dims are threaded correctly (`{'nlay': 25, 'nrow': 90, 'ncol': 78, 'nodes':
175500, 'ncpl': 7020}` at the point `Child_GN.rch` loads -- no cross-model
dims leakage). The mismatch is in the fixture itself:
`Child_GN.rch.rech.ref` (the child's `OPEN/CLOSE`-referenced RECHARGE
array) contains exactly 26901 values -- the *parent* grid's total node
count, not the child's 7020-per-layer count. Read the referenced file
directly to confirm: it's really that many values, not a
parsing-side miscount. Same disposition as #3/#11 -- a mismatched/stale
fixture pairing (the ref file seemingly belongs to a different grid than
the model referencing it), not a flopy4 gap; there's no principled way to
reshape 26901 real values into a 7020-shaped slot. Left `xfail`.

## 13. `OPEN/CLOSE ... (BINARY)` griddata arrays — never a corpus failure, IMPLEMENTED 2026-09-11 anyway

Not one of the 108 originally-cataloged failures -- `_read_open_close_values`
had an explicit `raise ValueError(... "BINARY arrays are not supported
yet")` guard from the gap-#2 pass onward, and 0/242 corpus models ever
hit it (checked directly: searched every `.oc`/griddata-bearing file in
the corpus for `OPEN/CLOSE ... (BINARY)`, zero matches). Implemented
anyway on request, since real MF6 input can use it even though this
corpus never exercises it.

**Format**: MF6's binary-array record is a 52-byte header (`KSTP`,
`KPER` int4; `PERTIM`, `TOTIM` float8; `TEXT` 16-byte label; `NCOL`,
`NROW`, `ILAY` int4) followed by `NROW*NCOL` values -- real arrays
double-precision, integer arrays 4-byte. This is the exact layout
flopy4's own binary head-output reader already decodes
(`utils/heads_reader.py::read_hds_timestep`, `f.seek(52, 1)  # skip
kstp, kper, pertime`) -- MF6 has used one binary 2D-array record format
for both real and integer arrays since MODFLOW-2005 (`u2drel`/`u2dint`),
for output and OPEN/CLOSE (BINARY) input alike.

**Verification, given no real fixture exists**: wrote a synthetic file
in this exact format and round-tripped it directly through
`_read_open_close_values` (real + integer + FACTOR-scaled), then
end-to-end through `Dis.load()` with a real `.dis` file referencing a
synthetic binary TOP array, confirming the values it produces match
what was written byte-for-byte. Added 3 permanent regression tests
(`test/test_package_load.py`) covering a plain real array, an integer
array with FACTOR, and a LAYERED field with one binary file per layer
(matching the existing per-layer text-CONSTANT/INTERNAL convention).
Corpus-wide: unchanged (239/242, expected -- nothing in the corpus
exercises this path either way), zero regressions.

**Update -- verified against real MF6 fixtures**: `../modflow6/autotest`
(a sibling checkout of the actual MODFLOW 6 Fortran repo) has
`test_gwf_utl01_binaryinput.py`, MF6's own test for binary array input,
covering both shapes real MF6 supports -- one binary file per layer, and
one flat file spanning all layers. Ran its `build_models()` directly
(real `flopy` 3.10.0, `flopy.utils.BinaryHeader.create(bintype="HEAD",
...)` / `Util2d.write_bin`, the actual writer real MF6 reads output
from) to generate real fixtures, then loaded both through
`Simulation.load()`. Confirms the header format guess above exactly:
`bintype="HEAD"` is the same record layout. Values matched what
`build_models()` wrote in every field (top, botm, idomain, icelltype,
strt) for both fixtures.

This also caught a real, separate bug the synthetic-only testing had
missed: flopy3's writer quotes OPEN/CLOSE filenames (`OPEN/CLOSE
'top.bin' ...`), and `word`'s tokenizer keeps the quote characters as
part of the token (`'` is a valid filename character in the class), so
`workspace / "'top.bin'"` (quotes and all) never resolved. Fixed with a
new `_strip_quotes()`, applied to both griddata (`_read_open_close_values`)
and list/period (`_resolve_open_close_rows`) filename resolution --
this affected the plain-text OPEN/CLOSE path too, not just BINARY,
though 0/242 corpus fixtures happened to hit it on a *recognized*
field (35 corpus lines do quote an OPEN/CLOSE filename, but all 35 are
for a DISU `AREA` field flopy4 doesn't have a hand-written class for
yet, so the row is skipped before the filename is ever resolved --
confirmed by checking directly, not assumed). Added a 4th regression
test (quoted single-quoted filename, both binary and text). Corpus-wide:
unchanged, 239/242, zero regressions -- consistent with that "never a
recognized field" finding. Full suite: 647 passed (+4 total from this
gap), same 7 pre-existing unrelated failures.

No longer flagged as unverified -- confirmed against MF6's own binary
IO round-trip.

## Noted in passing, not confirmed as any of the 108's root cause

- `.obs` files (observation-package input) fail to parse at all:
  `UnexpectedToken: Unexpected token Token('CNAME', 'FILEOUT') at line 4`
  — seen on `test001e_UZF_3lay.obs`. Not necessarily on the load path
  today (OBS attachment might not go through `_resolve_bindings` at all
  yet), so didn't affect any of the 108 directly, but worth a look if/when
  OBS loading is wired up.
- ~~Time-series (`.ts`) files use `!` as a comment/header marker (`!  time
  rate_1  rate_2`), which `SH_COMMENT` (`#`-only) doesn't recognize.~~
  **Resolved.** `basic.lark` and `typed.lark` ignore a `BANG_COMMENT`
  (`/![^\n]*/`), whole-line or trailing (since #395), and TS6 files load as
  `Ts` children. The TS models (test027_TimeseriesTest, test001e_UZF_TS,
  test001e_UZF_3layTS, test020_NevilleTonkinTransientTS, test051_uzfp2TS)
  are in `KNOWN_PASSING`.
