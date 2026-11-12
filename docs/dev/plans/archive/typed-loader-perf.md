# Loader performance

**Status (2026-10-19): all of the work below is merged, and optimization
is paused.** The branches named in the sections below landed as #474
(`numeric-runs`, approach 1), #479 (`item-table`, approaches 5 and 6,
with `list-ingress` folded in), #480 (`load-perf`), #481
(`load-snapshots`, step 0), #483 (`load-memory`, M1-M4 and the mapped
read) and #484 (`load-simplify`, which merged the readers' number
conversion and `read_table`/`read_ragged` into `read_rows`). Benchmarks
are in `benchmarks/` (#482). What's left is under "Paused: what remains".
Branch names, commits and "no PR yet" notes further down are history.

Both readers (`loads_basic`, which real loads use, and `loads_typed`, the
per-component generated grammars) make one lexer token per value, and the
typed reader also builds two subtrees per value. On the corpus's big
files this dominates CI. Each `test1002_biscqtg_disv*` case in
`test_load_simulation` takes ~5.3 min on an ubuntu runner (it runs the
typed parse too for known-passing models, see `_check_typed_grammar`).
Those cases set the CI floor even with `--dist worksteal`.

## Measurements

Local (macOS), parser already built.

`biscayne.riv` from `mf6/large/test1002_biscqtg_disv_dev`: 57 MB, 1.27M
list rows (`1  42622  0.245364  76175.2  -4.13766`), ~6.3M values.

|       | lex    | parse (lex + tree) | tree nodes | transform |
|-------|--------|--------------------|------------|-----------|
| basic | 10.4 s | 32.8 s             | 1.27M      | 4.0 s     |
| typed | 12.3 s | 78.3 s             | 13.9M      | 33.6 s    |

The same rows read without Lark: `[l.split() for l in text.splitlines()]`
takes 1.3 s. Converting the five columns with numpy (`astype(int)` /
`astype(float)` per column) takes another 0.4 s. Per-value
`_NUMBER.fullmatch` + `parse_number`, as basic's `TOKEN` callback does,
takes 3.1 s.

`secp_mf6.npf` from `mf6/large/test1005_secp`: 28.9 MB, 48 INTERNAL
arrays, 1.7M values.

| reading the arrays with                    | time          |
|--------------------------------------------|---------------|
| basic parse + transform                    | 6.5 s + 0.8 s |
| typed parse + transform                    | 9.8 s + 1.1 s |
| `np.array(s.split(), dtype=float)`         | 0.10 s        |
| `np.fromstring(s, sep=" ")`                | 0.14 s        |
| one `re.finditer` for the numeric-line runs | 0.31 s        |

`biscayne.disv` (9.4 MB) is **not** an array file: its griddata are all
OPEN/CLOSE, which ingress already reads with numpy
(`converter/ingress/structure.py:153`). Its size is the VERTICES and
CELL2D lists. Basic takes 6.0 s parse + 0.8 s transform, and typed takes
15.5 s parse + 7.1 s transform.

A `cProfile` of the typed transform on a 100k-row slice of the riv file
(~500k values) shows ~1.1M user callbacks, ~1M
`TypedTransformer.__getattr__` calls, and ~500k `__default__` +
`parse_rule_name` calls, all for the per-value nodes.

### Where the values are

The largest corpus files are list rows. The biscqtg `.riv` files are
57 MB each, and there are 8 of them. Files with the most INTERNAL array
values:

| INTERNAL values | file                                                  |
|-----------------|-------------------------------------------------------|
| 1,716,000       | `mf6/large/test1005_secp/secp_mf6.npf` (28.9 MB)      |
| 1,347,525       | `mf6/large/test1001_Peterson/v6.evt`                  |
| 1,179,750       | `mf6/large/test1005_secp/secp_mf6.dis`                |
| 1,017,600       | `mf6/test/test016_Keating_disu_mfusg/keating.disu`    |
| 898,350         | `mf6/large/test1001_Peterson/v6.dis`, `v6.npf`        |
| 795,324         | `mf6/test/test016_Keating_disu_mfusg/kzusg.disu`      |
| 582,025         | `mf6/large/test1000_751x751*/mfusg_C.npf`, `.ic`      |

In CI (PR #472, ubuntu 3.11), the array-heavy models cost ~4–5 min of
worker time: Peterson 84 s, secp 66 s, and Keating ~84 s over the load and
round-trip tests. The list-heavy biscqtg cases cost ~32 min (six disv
variants at ~5.3 min each, and two dis variants at ~2.5 min each).

## Root causes

1. **One token per value (both readers).** The lexer makes a token for
   every number, and each token costs a regex match, a `Token` object and
   (in basic) a `TOKEN` callback. That is ~10 s of lex alone on
   `biscayne.riv`, before any tree. Building the tree on top of that is
   most of basic's ~33 s parse.

2. **Per-value subtrees (typed only).** In `grammar/typed.lark`:

   ```
   record: token (token | block_kw_word)* _NL
   token: number | word
   number: SIGNED_NUMBER | NUMBER
   word: WORD_STR | QUOTED
   ```

   Every list value becomes `token -> number|word -> TERMINAL`, two
   subtrees per value (~11 nodes per 5-value row vs basic's 1 `line`
   node). Arrays have a smaller version of this: `_data_line: double+`
   is one `double` subtree per value.

3. **Slow per-node dispatch (typed only).** Rules imported from
   `typed.lark` are namespaced in the generated grammars (`typed__token`,
   `typed__number`, `typed__double`, ...). Lark looks up a callback by
   that name. The lookup misses and hits `TypedTransformer.__getattr__`
   (`transformer/typed.py:49`), which strips the prefix and retries.
   `token` has no callback at all, so that lookup raises
   `AttributeError` and Lark falls back to `__default__`
   (`typed.py:302`). That runs `parse_rule_name` on the rule name, finds
   no tags, and builds a `Tree` anyway. `record` (`typed.py:220`) then
   unpicks those `token` trees by hand. All of this happens once per
   value.

4. **Building the tree at all.** Both readers build a full parse tree and
   then transform it.

## Approaches

In order. Approach 1 removes cause 1 for the big files and most of 2–4
along with it, because the per-value tokens and nodes are gone. Approaches
2–4 still help the typed reader and smaller files, but they matter much
less once 1 lands. Measure again after 1 before you start them.
Approach 5 (list rows by column, in ingress) came out of profiling after
1. It's what's left of biscqtg's load time, so it comes next. Approach 6
(store tabular lists as columns) came out of benchmarking after 5. It's a
change to how packages hold list data, not just to loading.

### 1. Lex runs of values as one terminal, convert with numpy (both readers)

**Status: step 1 done for the basic grammar** (branch `numeric-runs`,
commits f4b44eeb + 7fe4b112 (rename to `NUMBER_LINES`), pushed to the fork, no PR yet; worktree `.claude/worktrees/numeric-runs`). The `NUMBER_LINES`
terminal is in `basic.lark`, and its callback in `transformer/basic.py`
gives the same rows as `line`. It also takes the blank and comment-only
lines after a numeric line, as `line`'s `_NL+` does. Without that, a
comment after a run gave an extra empty row (seen in
`test001a_Tharmonic_tabs/flow15_constant.chd`). Output matched the old
grammar exactly, by `repr`, on 143 files from 10 sample models and on 8
edge-case strings. The basic parse on that sample went from 100 s to
7.6 s. Full `Simulation.load`, old → new:

| model | total | basic parse | rest |
|---|---|---|---|
| test1005_secp | 19.8 → 2.4 s | 18.6 → 1.1 s | 1.2 s |
| test1001_Peterson | 23.5 → 5.5 s | 20.0 → 1.9 s | 3.5 s |
| test1002_biscqtg_disv_dev | 73.0 → 30.8 s | 44.6 → 2.9 s | 28 s |

Parsing is no longer the cost. Step 2 below (numpy in ingress) would
save little, since converting values isn't what's slow. biscqtg's 28 s
is building one object per list row, so approach 5 is next. The typed
grammar's version of this is still to do.

Lex a whole run of number-only lines as **one** token, then convert it in
bulk. numpy can parse the 1.7M secp values in 0.1 s, and Python can split
the 1.27M riv rows in 1.3 s. Lark spends 7–11 s and ~37 s on those files.

**Basic grammar first.** It is the real load path (Simulation.load →
`Package.load` → `_codec_load` with no component), so it helps users and
every load test.

- Add a terminal for one or more consecutive lines made of numbers only,
  e.g. (sketch, not checked against every edge):

  ```
  NUMBER_LINES.2: /([ \t]*[+-]?(\d+\.?\d*|\.\d+)([eEdD][+-]?\d+)?([ \t,]+[+-]?(\d+\.?\d*|\.\d+)([eEdD][+-]?\d+)?)*[ \t,]*\r?\n)+/
  ```

  Then allow it in a block body: `_list: (line | numeric_run)*`. The
  value pattern must accept exactly what `_NUMBER` in
  `transformer/basic.py` accepts (including Fortran `D` exponents), so no
  value changes type.
- This one terminal covers INTERNAL array data (and keyword-less data
  rows) **and** all-numeric list rows like `biscayne.riv` and DISV
  VERTICES/CELL2D. Any line it can't take falls back to `line` as it
  does today, so correctness doesn't depend on catching every case. Lines
  that fall back include rows with a boundname, a quoted value, a
  comment, a remark, or a keyword.
- **Lexer behaviour to check first.** Lark's basic/contextual lexer
  joins the allowed terminals into one regex alternation sorted by
  priority, then by pattern width. It is not true longest-match, so the
  run terminal needs a priority above `TOKEN` (0) and `QUOTED` (1) to be
  tried first. With the contextual lexer it only competes in states where
  a body line can start. The regex must end at a newline, so it can never
  take part of a line and leave the rest. Check `BEGIN`/`END` (an `END`
  line isn't numeric, so it ends the run), `\r\n` endings, blank lines
  inside a run (common's `NEWLINE` swallows several newlines in one
  token), and leading whitespace. Also check the tokens before the
  run: the block name line's trailing `_NL` must not eat the run's first
  line.
- **Representation, in two steps:**
  1. The callback (`def NUMBER_LINES(self, tok)` with
     `visit_tokens`, or a `numeric_run` rule callback) expands the run
     into the same `list[list[int | float]]` rows `line` gives today. This
     needs no ingress change and removes the parse cost, which is the big
     part (~33 s → a few seconds on riv). Convert per row with
     `str.split` + a fast int/float conversion. Keep `parse_number`'s
     semantics: an integer-looking token stays `int`, `1.0` stays
     `float`, and `D` exponents work.
  2. Hand ingress the raw run instead (e.g. a small `NumericRun(text)`
     wrapper in the block's row list), and convert it where the dtype is
     known. `_read_control_record` (`structure.py:271`) can then do
     `np.array(text.replace(",", " ").split(), dtype=dtype)`, or the same
     with `D`→`E` when the text has a `D`. That is what
     `_read_open_close_values` already does at `:153`. It must still read
     exactly `length` values and continue after them. One run can hold
     the end of one array's data, but not the next control record, which
     isn't numeric. List-row ingress can convert by column
     (`np.array(rows)` → `astype` per column) instead of by value. This
     step touches every consumer of block rows, so do it only where the
     profile says the per-row conversion still matters.
- **Memory:** a run token holds the whole run's text, which can be tens
  of MB. That's fine, because it is smaller than millions of `Token`
  objects.

**Typed grammar after.** Replace `data: _data_line+` with a run terminal
and convert it in `data()` with one `np.array(..., dtype=float)`. This
covers `_data_line`'s `[_remark]` by fallback, or keep `_data_line+` as
an alternative for remarked lines. Typed list rows (`record`) could take
the same run terminal, giving rows of numbers, but this interacts with
the generated grammars' per-field rules. Look at how `stress_period_data`
and the `*__fields` rules use `record` before you choose.

**Edge cases the current grammars handle that the run must too (or fall
back on):** comma separators (`1.0,1,1.0`), trailing `#`/`!` comments
and bare remarks on a data line, `D` exponents, a value like `1.` or
`.5`, signed values, and the whole-token rule (a token like
`1997-07-16T19:20:30` is a word, not `1997` and so on). The run regex's
per-value lookahead is what enforces that rule, as `(?![^\s,#!])` does
for the existing terminals.

### 2. Inline the per-value rules (typed only)

Make the per-value rules inline so their one child goes straight into the
parent: `?token: number | word`, and the same for `number`, `double` and
`integer` where possible (`?rule` inlines when it has one child, which
these always do). Then convert terminals where they land instead of in
per-rule callbacks:

- `record` gets raw `Token`s (`NUMBER`, `SIGNED_INT`, `WORD_STR`,
  `QUOTED`, namespaced as `typed__NUMBER` etc.) and converts each by type
  (`parse_number` for numeric terminals, `unquote` for words).
- Or use terminal callbacks (`visit_tokens=True` with
  `def NUMBER(self, tok)`, plus the `typed__` names). That is cheaper
  than a subtree but still one call per value.

Watch out:

- Inlined rules never call their own callback, so the conversion in
  `number()`/`double()`/`integer()`/`word()` (`typed.py:184-200`) must
  happen somewhere else for every place these rules appear. In the
  generated grammars, `word` is used 561 times, `integer` 434, `double`
  374, `number` 258 and `string` 357 (`token` appears only via
  `record`). Options fields like `maxbound__val: "maxbound"i integer`
  rely on `integer` returning an `int`.
- `double`, `number` and `integer` mean different conversions (always
  float, int-or-float, and int). An inlined `double` loses that unless
  the parent knows its field type. It may be simplest to inline only
  `token` and `number` inside `record`. Approach 1 already covers
  `_data_line`'s `double+`.
- The transformer types each value in a record by whether it is a
  `word` or a `number`. Keep the conversion behaviour identical: ints
  stay ints, `1.0` stays float, and quoted strings are unquoted.

Expected: a typed tree size near basic's, and most of the 33.6 s
transform gone, for rows approach 1 doesn't take.

### 3. Make transformer dispatch cheap (typed only, small)

Every remaining namespaced node pays the `__getattr__` miss. Instead:

- Define the `typed__*` callbacks explicitly (e.g. bind
  `typed__record = record` etc. on the class, or generate them in a loop
  at class-creation time) so Lark's lookup hits directly.
- Cache `parse_rule_name` results (`grammar/names.py:40`) by rule name,
  e.g. with `functools.lru_cache`. There are only a few hundred distinct
  rule names.
- Give `token` a callback if it stays a subtree, so it never goes through
  `AttributeError` + `__default__`.

Cheap to do and safe. It can land with any of the others.

### 4. Transform while parsing (both readers)

With LALR, `Lark(grammar, parser="lalr", transformer=t)` calls the
callbacks as rules reduce and never builds the tree. After approach 1
the trees are much smaller, so this is worth less. Profile first.

Caveats to check first:

- Lark builds the in-parse callbacks with `getattr(transformer,
  rule_name)` and builds a plain `Tree` when that's missing. As far as I
  know it does **not** route missing names to `__default__`. If so, the
  typed transformer's `__default__`-driven generated rules (`*__block`,
  `*__fields`, `*__val`, ...) would come back as Trees, and
  `__getattr__` would need to return a `__default__`-backed callback for
  every name. Verify this against the installed Lark version
  (`lark/parse_tree_builder.py`).
- In-parse callbacks get only `children` (no `meta`) unless wrapped with
  `v_args`. Check that `__default__`'s use of `meta` still works.
- The parsers are cached and shared (`get_typed_parser` is
  `lru_cache`d, and `BASIC_PARSER` is module-level), so the transformer
  must be stateless. `_TYPED_TRANSFORMER` looks stateless now. Keep it
  that way.
- A parser built with a transformer can't also return a plain tree.
  Check that nothing calls `.parse()` and expects a `Tree`, including
  tests and the trailing-garbage retry in `loads_basic`/`loads_typed`.
- Error behaviour: an exception inside a callback now fires mid-parse,
  not after. The `LarkError` catch + `_trim_trailing_garbage` retry in
  `codec/reader/__init__.py` must still behave.

### 5. Build list data by column, not one Item per row (ingress, both readers)

After approach 1, biscqtg_disv's load is 2.9 s of parse and 28 s of
everything else. The time goes to `biscayne.riv`'s ~1.27M period rows
(1.51M list rows in all). From a cProfile of `Simulation.load` (97 s
under the profiler):

- `_parse_rows` (`converter/ingress/structure.py:51`) calls
  `Item.from_tokens` once per row: 77 s cumulative.
  - `_layout` (`item.py:460`), 53 s. This includes `solve`/`first`
    (`:602`/`:620`), 24 s, and `options` (`:507`), 14.6M calls.
  - The attrs `__init__` of `Riv.StressPeriodData`, 19.5 s. This
    includes `__attrs_post_init__` → `_counted_fields` (`:87`),
    `_sized_by_field` and `attrs.fields_dict`, 13M calls.
  - `_convert` (`:663`), 16 s, and `_has_boundname_field` (`:126`),
    6 s.
- `Package.__attrs_post_init__` (`package.py:75`), 15.5 s. This includes
  `_set_child_parents` → `_period_row_children` → `_row_children`
  (`component.py:140-161`), 9.7 s, and `_init_item_lists`
  (`package.py:127`), 5.8 s.

Almost all of that work is the same for every row of a **tabular list**.
That is a list block whose rows all have one record type: no unions or
keystrings, no child columns, the same width in every row (riv's period
data, packagedata, DISV's VERTICES/CELL2D). Its rows share a layout: the
same columns, the same cellid width, and whether there's a boundname.
Their values don't change it.

- **Scope: list packages only.** Grid- and layer-array packages (RCHA,
  EVTA, the grid-based CHDG/WELG and so on) already hold arrays and read
  them by column through array ingress (`_read_control_record`). They
  never build per-row Items, so this doesn't touch them.
- **What it builds:** the same `list[Item]` the generated class holds
  (`Riv._stress_period_data: dict[int, list[StressPeriodData]]`), just
  built faster. Going straight to columns would mean changing that
  representation, which is out of scope here. The xarray form in
  [`period-lists.md`](period-lists.md) is a view derived from the list (`to_xarray`),
  not storage, so it doesn't change this.
- **Fast path:** lay out the first row with `_layout` as now and check
  that the block is a tabular list. Every row must have the same token
  count, and every value column must be numbers only. A time-series name
  is a word in a `Union[float, TimeSeriesRef]` column, so a block with one
  takes the slow path, and a fixed-position boundname word is fine. If the
  block qualifies, convert by column once (`np.array(rows)` or per-column
  slices → int cellids minus 1, floats). Then make each Item with a cheap
  constructor that skips `_layout` and the per-row `__attrs_post_init__`
  checks: one `cls(**kwargs)` from precomputed column slices, or
  `object.__new__` plus field sets if attrs validators/converters cost
  too much. Anything that doesn't qualify falls back to `from_tokens` per
  row, as now. Profile the cheap constructor first. If attrs `__init__`
  alone is most of the 19.5 s, the Item-per-row representation is the
  floor, and changing it is a separate decision.
- **Per-row checks that move to per-block:** `_counted_fields`,
  `_has_boundname_field` and the `fields_dict` lookups depend only on
  the class, so cache them per class (`functools.cache` on the class)
  whatever else happens. That alone is a cheap first step. Measure it
  before the column path.
- **`_set_child_parents`:** `_row_children` walks every row's fields to
  find child components. A class with no child fields (directly or in a
  nested record) can't have any, so check that once per class and skip
  the walk.
- **Validating:** the equivalence check compares the loaded package's
  rows, or its period data, old vs new, on riv/disv (biscqtg), wel/chd
  with boundnames, a list with unions (SFR/MAW/LAK), and a list with
  child columns (LAK's TAB6). Then run the load tests for those models.

**Status: done, differently from the fast path sketched above.** It's on
branch `list-ingress`, commit `77b67374`, in the
`.claude/worktrees/numeric-runs` worktree, rebased onto develop `6f456c65`
(after #474, approach 1) and pushed to `origin/list-ingress` (no PR yet).
The rebase kept #473's conditional-options check in `_coerce_item_list`,
for loaded Items too, checking only options not set yet. It merges cleanly
with `period-lists` (#476).

- **Not by column.** Profiling after the caching step showed attrs
  `__init__` is cheap: 2.9 s profiled for the 1.27M riv rows, so it isn't
  the floor. The cost was `_layout`'s search plus `_convert`'s generality.
  So rows keep being read one at a time, but by a plan:
  - `_layout` is split into `_solve` (the search) and `_convert`.
  - `Item.from_rows` lays out the first row of each length with `_solve`.
    `_plan` turns that layout into column positions and a reader for each
    field.
  - Each later row of that length is read by the plan, then built with
    `cls(**kwargs)`.
- **Which classes:** `_plannable` admits a class only if its layout depends
  on the number of tokens alone: no keyword, flag, count column (cell2d's
  ncvert), untagged unions, child column, or union-arm `rest`. A boundname
  is fine, and so are time-series names: the reader converts them as
  `_coerce` does, so they don't force the slow path.
- **Fallback:** a row the plan's readers can't convert (a NONE cellid as
  wide as a DISU node) falls back to `from_tokens`.
- **Also in the commit:**
  - `_counted_fields` and `_has_boundname_field` are cached per class.
  - `_row_children` skips classes that `_may_hold_children` says can't
    hold a child.
  - `_coerce_item_list` skips `_row_context` when rows are already Items.
    That was a 5 s profiled hidden cost: `resolve_dims` was walking all
    1.28M rows per period, with a runtime-Protocol `isinstance` on each.
- **Equivalence:** I loaded each sim with the plan off and on and compared
  every field. All 16 copied models matched: the 10 earlier sample models,
  plus lake1ss_table (TAB6), sfr_mvr (wel boundnames, SFR, MVR),
  mawconfined, NWTP3Low_MAW, lake2tr, and mvlake_laksfr_tr. A deliberate
  perturbation of the fast path's readers showed up as diffs, so the check
  bites.
- **Tests:** `test_rows_as_each_row_reads` was added. The codec,
  component, roundtrip, reader, dimensions, load-context and namefile
  tests pass.

| Model | Approach 1 | + approach 5 |
|---|---|---|
| `mf6/large/test1002_biscqtg_disv_dev` | 30.8s | 8.0s |
| `mf6/large/test1001_Peterson` | 5.5s | 4.4s |
| `mf6/large/test1005_secp` | 2.4s | 1.7s |

What's left in biscqtg's 8 s:
- the basic parse, 2.7 s, of which `NUMBER_LINES`' callback is about 1 s;
- 106k rows of DISV's CELL2D, which still take `from_tokens` because it
  has a count column (ncvert), about 1.8 s;
- `_file_cellid` and the riv attrs `__init__`, about 1 s each.

A count column could be planned when the count is the only thing that
varies by value, but that's not done.

### 6. Store tabular lists as columns, not one Item per row

Approach 5 still converts each value in Python (the `NUMBER_LINES`
callback, then the plan's readers) and still makes one Item per row.
Converting by column only pays off fully if the columns are what's
stored.

**Benchmark** (`biscayne.riv`'s 100 period blocks, 1,267,300 rows; each
path's output checked equal to A's; lexing not included, it's the same for
all three; script `scratchpad/runs/colbench.py`):

| Path | Steps | Time |
|---|---|---|
| A. now (approach 5) | `NUMBER_LINES` callback 1.29 s + `from_rows` 2.40 s | 3.69 s |
| B. columns → Items | `np.fromstring` + reshape 0.46 s, `astype` per column ~0 s, `tolist` + `cls(**kw)` 1.86 s | 2.32 s |
| C. columns stored | `np.fromstring` + `astype`, no Items | 0.47 s |

B saves ~1.4 s, and its floor is making the Items (1.86 s). C saves ~3.2 s
on riv alone, before the per-row costs after ingress
(`__attrs_post_init__`, item-list init, writing) that it also removes.

**Why not just use the grid packages.** CHDG/DRNG/GHBG/RIVG/WELG
(`readarraygrid`) and RCHA/EVTA (layer arrays) already store
`dict[kper, array]`, but dense over the grid. A RIV file is list input and
loads as RIV, and the dense form can't hold two rows in one cell, or
per-row boundnames or time-series names. Columns are the sparse
counterpart. They still follow the DFN: a list block is a record type with
a column per field, and Item-per-row and array-per-field are two layouts
of that one schema (flopy3's recarrays were the column layout).

**Container.** `ItemTable[X]`, one per period: a numpy array per field of
`X`, keyed by field name.
- `cellid`: `(n, ncelldim)` int, 0-based; NONE as a sentinel
  (`FILL_INT64`).
- Value columns: float64. `aux`: `(n, naux)`.
- `boundname`: a str array, or None if no row has one.
- Time-series columns: floats with NaN where a series applies, plus a
  parallel array of series names, as [`period-lists.md`](period-lists.md) lays out for
  xarray.

That's close to period lists' `sparse=True` form, so `to_xarray` becomes
almost a copy.

**Scope.** Only classes `_plannable` admits. Union rows (SFR/MAW/LAK
periods, OC), child columns (TAB6) and count columns (CELL2D's ragged rows)
stay `list[Item]`. Two representations is the main design cost, but it's
the split approach 5 already makes.

**Row access, in-place edits included.** `ItemTable` acts as a
`Sequence[Item]`: `len` (so `maxbound` works), iteration, `==` against a
list of Items, and `t[i]` returning a **row view** that writes back. A
prototype (`scratchpad/runs/rowview.py`) shows this works with attrs:
- The view class is a subclass of `X`, made once per class, with
  `__slots__ = ("_table", "_i")` and a property per column field. It's
  built with `object.__new__`, skipping `__init__`.
- `isinstance(view, X)` holds, so code that checks the Item class keeps
  working.
- `view.stage = 3.5` and `view.cellid = (1, 9)` go through attrs'
  generated `__setattr__` (its `on_setattr` converters and validators),
  then the property writes into the column.
- Making 1M views takes 0.23 s, so building one per access is cheap.
- **Equality fails.** attrs' `__eq__` requires `other.__class__ is
  self.__class__`, so a view never equals a plain `X`. The view class needs
  its own `__eq__` comparing field values against `X` or another view.
- **Still to decide:**
  - assigning a `TimeSeriesRef` into a float column (it also has to set
    the names array);
  - a value for a column that's absent (`boundname` when None: allocate
    it);
  - a cellid of another width;
  - `append`/`insert` (concatenate; O(n), fine for occasional edits);
  - `t[i] is t[i]` is False.

**Load path.**
- `NUMBER_LINES` also keeps the token's text.
- For a tabular class with a fixed row width, ingress runs `np.fromstring`
  and slices columns at the `(a, b)` positions `_plan` already computes for
  each field.
- Blocks with words in them (boundnames, time-series names) go through a
  str array and convert by column: still a table, just slower.
- The typed transformer (`codec/reader/transformer/typed.py`) needs the
  same.

**Uses of item lists to switch over:**
- Writing: `converter/egress/unstructure.py` calls `to_tokens` per row;
  write columns in bulk instead.
- User input: `Package._coerce_item_list`/`_items_from` (Items, tuples,
  dicts, dict-of-lists, DataFrames) all produce a table. Dict-of-lists is
  columns already.
- `to_dataframe`/`from_dataframe` become nearly trivial.
- `period_lists.py` (PR #476) reads rows with `getattr` per row: read
  columns instead.
- Boundnames and conditional options: one test per column.
- `_row_children` skips tables. The dimension walk treats a table as one
  element.
- `adapters.py`: flopy3 wants recarrays, so it gets simpler.
- Codegen: the 95 `list_(` fields' types go from `list[X]` to
  `ItemTable[X]` (or `Sequence[X]`).

**Validating.** The plan-off/plan-on equivalence script (`eqfast.py`),
comparing through `ItemTable == list[Item]`, plus the codec, roundtrip and
period-lists tests.

**Order.**
1. `ItemTable` plus the load path, turned back into Items at the end so
   nothing downstream changes. That's B's ~1.4 s.
2. Store tables, with row views, and switch the uses above over one at a
   time: writing, DataFrames, `to_xarray`.
3. Codegen types last.

**Progress** (branch `item-table`, on `list-ingress`, on develop
`49f9daf3`; both pushed to the fork, no PRs).
- Step 1, `e9d68f35`: `NUMBER_LINES` keeps its text (`NumberRows`,
  converted only when read); a block of only such lines reaches
  `_parse_rows` as is, and `read_table` reads it by column.
- Step 2, `bf5fbbf6`: tables are stored, loaded or given (any class
  `_plannable` admits). `ItemTable` is a `MutableSequence`.
  - A row is a view: a subclass of the Item class, of the same name, with
    a property per field. It sets through attrs' converters and
    validators, compares equal to the Item, and copies or pickles as one.
  - A value a column can't hold (a time-series name, a boundname) makes
    that column objects. Signed-index fields (SFR's `ic`) aren't read by
    column.
  - Switched over: writing (`ItemTable.tokens`), `to_dataframe`, setting
    options and dimensions from rows, the time-series and boundname
    checks, the dimension walk.
  - Fixed on the way: SFR's `_check_lookup_counts` scanned packagedata per
    row (quadratic; with views, Peterson's load took 36.6 s). It now
    indexes the rows once.
  - biscqtg: load 8.7 s → 4.0 s, write 10.4 s → 3.1 s. Loads equal and
    written files byte-identical on all 16 corpus models (scripts
    `eqtable.py`, `eqwrite.py`, `eqframe.py`).
  - Behavior changes: a user's Items are copied into the columns, so
    editing one afterwards doesn't change the package (edit
    `pkg.stress_period_data[k][i]`); `t[i] is t[i]` is False; a
    non-period table (packagedata) is a leaf in `attrs_to_datatree`, so a
    dataset attribute, not a node per row.

**Next: `period_lists` (#476) by column.** It loops over rows
(`to_dataset`'s events, `_to_sparse`'s `put`), which views make slower.
On biscqtg's RIV (1,267,300 rows, `duplicates="last"`; script
`xrtime.py`):

| `to_xarray` | Item lists | tables |
|---|---|---|
| dense | 3.9 s | 6.8 s |
| sparse | 8.1 s | 13.4 s |

Give it a column path for `ItemTable`s, keeping the row loop for lists of
unions and plain Item lists:
1. Sparse. Concatenate each column across periods, `per` from the period
   lengths. Split cellid `(n, ncelldim)` into the cell coordinates and aux
   `(n, naux)` into one variable per name. Object columns become NaN plus
   `<name>_ts`.
2. Dense. Positions for a whole column at once from the cellid columns.
   Fill each period's state with fancy indexing. Duplicates by `np.unique`
   on positions: `first`/`last` by the index kept, `sum` with `np.add.at`,
   `raise` on any repeat.
3. `from_dataset` builds tables directly.

Validate: `Dataset.identical` between tables and the same package
`to_items()`'d, dense and sparse, every `duplicates` mode, on the corpus;
plus `test_mf6_period_lists.py`.

**Still open after that:** the typed transformer (`typed.py`) doesn't
keep block text; `adapters.py` could build recarrays from the columns;
step 3 (codegen types).

### Test-side (not an optimization)

The nine `test1002_biscqtg*` variants are the same big grid. The typed
parity check could run on one of them only, while the full load still
runs on all of them. That is independent of the above, and it's the
cheapest way to cut CI time if the loader work stalls.

## Status and next steps (2026-10-15)

Approaches 1, 5 and 6 are on `item-table` (`fa5103ba`), approach 1 in
both grammars. Measured locally on the 16 scratch corpus models, parser
built and imports warm.

Parse only, `loads_basic` vs `loads_typed`, 174 package files: basic
parses all of them, and typed fails 6 (`sln-ims` ×5 and `gwf-lak` in
mvlake, the known gaps). On the 168 both parse, basic takes 3.85 s in
total and typed 6.17 s. Typed is within 0.8–1.3× basic on the big array
files (e.g. `biscayne.riv` 0.82 s vs 0.85 s, down from 32.8 s / 78 s).
Most of the remaining difference is per-component parser builds
(0.02–0.15 s each) plus one file:

- `v6.sfr` (Peterson, 3 MB): basic 0.70 s, typed 2.07 s. Its
  packagedata/connectiondata mix words and ragged rows, so they miss
  `NUMBER_LINES` and go through `record` per value.

Full `Simulation.load` vs flopy3 3.11 `MFSimulation.load`. flopy3 reads
OPEN/CLOSE arrays on access, so the second flopy3 time also reads every
data item:

| model          | flopy4 (parse) | flopy3 | flopy3 + read all |
|----------------|----------------|--------|-------------------|
| biscqtg_disv   | 3.96 s (1.00)  | 8.84 s | 10.76 s           |
| secp           | 1.41 s (1.02)  | 2.38 s | 2.46 s            |
| Peterson       | 3.21 s (1.71)  | 2.90 s | 3.02 s            |
| 13 small ones  | 0.01–0.03 s    | 0.01–0.07 s |              |

Next:

1. Profile Peterson's load. It's the one model where flopy4 isn't
   faster: half of its 3.1 s is parsing (`v6.sfr` 0.7 s of that), plus
   1.4 s after the parse. Find out what the 1.4 s is (SFR ingress?
   structuring?).
2. Typed `record` path for mixed/ragged list rows (the SFR gap). Either
   a run terminal that allows words, or splitting such rows as text in
   the transformer the way `NumberRows` does.
3. Re-check the CI time of the `test1002_biscqtg*` cases once the
   branch's CI has run, and decide whether the test-side trim below is
   still worth it.
4. Later, optional: deferring OPEN/CLOSE reads until access, as flopy3
   does. It doesn't help Peterson (only its DIS is external).
5. Deferred, as before: `adapters.py` recarrays, and step 3 (codegen
   types).

Scripts: `scratchpad/runs/tvb.py` (parse, per file), `vs3.py` and
`vs3full.py` (vs flopy3), all in the session scratchpad.

### Done (2026-10-15, later)

On `item-table`, local commits `b6889388`..`f7f111de`. Loaded values are
identical to `fa5103ba`'s on all 16 corpus sims (2719 fields digested), and
typed output is identical on all 174 files.

- **Step 1, profiled Peterson.** Two things after the parse:
  - Griddata number lines were flattened into Python lists and walked
    token by token (`_numeric_prefix`). Array blocks now keep each run
    as a `NumberRows` part (`BlockRows`) and read its text with numpy.
  - SFR's 41,844 period rows (`1 inflow 0.0`) each had their layout
    solved alone. `from_rows` now plans rows ending in a keyword union by
    length, plus each arm per length.
- **The same profile on biscayne** found its DISV CELL2D rows (106k,
  icvert counted by ncvert) also solved one by one. They're now planned
  by length, checking each row's count against the plan.
- **Step 2, typed rows with words.** Tried both:
  - A, a run terminal `RECORD_LINES`: v6.sfr typed 2.03 s -> 0.15 s
    (basic 0.80 s), corpus typed total 6.17 s -> 4.24 s.
  - B, one token per line: 0.38 s, 4.65 s.
  Kept A. A list sharing its block with other fields (sim-nam's
  solutiongroup, with MXITER) uses `token_record`, lexed by value.
  Grammars regenerated from the cached DFNs at modflow6 `524d1ace`, which
  reproduce the committed ones exactly.
- **Step 4, deferring OPEN/CLOSE reads:** not done. They cost flopy4
  0.08 s of biscayne's load and 0.02 s of Peterson's (numpy reads), so
  deferral isn't worth a lazy-field mechanism.

| model        | flopy4 before | flopy4 now (parse) | flopy3 |
|--------------|---------------|--------------------|--------|
| biscqtg_disv | 3.96 s        | 2.77 s (1.01)      | 9.02 s |
| secp         | 1.41 s        | 1.12 s (0.63)      | 2.44 s |
| Peterson     | 3.21 s        | 2.16 s (1.28)      | 2.97 s |

Noticed: the typed sim-nam transform keeps only `mxiter` from a
solutiongroup block and drops its rows (at `fa5103ba` too). Fixed below.

### Done (2026-10-15, evening)

Local commits `366fa2f5`, `b875d8e8` on `item-table` (not pushed). Loaded
values are still identical to `fa5103ba`'s on all 16 corpus sims.

- **Fix, typed solutiongroup rows** (`366fa2f5`). `_fields` skipped a
  list's rows (not a `(name, value)`) among named fields, so a
  SOLUTIONGROUP with MXITER lost its solutions. Rows are now kept under
  `stress_period_data` whether they come before or after MXITER.
  `test_typed_loads_record_lines` covers both orders.
- **`WORD_LINES` in basic.lark** (`b875d8e8`). Real loads parse with basic,
  where lines with a word on them (SFR's `1 inflow 0.0`) still took a token
  per value; #474's `NUMBER_LINES` only takes number-only lines.
  `WORD_LINES.1` takes a run of lines that each have a non-number token,
  beside `NUMBER_LINES`. Kept as two terminals, not one, so the lexer
  (C regex) does the number/word split that downstream needs anyway (array
  data read from `NumberRows` text, headers as word rows), and #474's path
  is untouched. Lines it can't take whole fall back to `line`, as before:
  - first token starting with `begin`/`end` (a prefix, not only the whole
    word, so they lex exactly as before);
  - a quote anywhere (quoting forces a string);
  - a trailing comment.

  `BasicTransformer.WORD_LINES` splits each line and converts each value
  with the same `_value` as `TOKEN` (`D` exponents included); `block`
  splices the rows in. Test: `test_loads_word_lines` in
  `test_mf6_codec.py`.

| model        | flopy4 before (parse) | flopy4 now (parse) | flopy3 |
|--------------|-----------------------|--------------------|--------|
| Peterson     | 1.95 s (1.29)         | 1.41 s (0.70)      | 2.89 s |
| biscqtg_disv | 2.62 s (1.03)         | 2.62 s (1.01)      | 8.99 s |
| secp         | 1.00 s (0.63)         | 0.98 s (0.61)      | 2.43 s |

`v6.sfr`'s basic parse alone: 0.68 s -> 0.09 s. "Before" is today's re-run
of the previous commit (this machine varies; it was 2.16 s for Peterson
earlier). flopy4 is now faster than flopy3 on all three.

Next:

1. Profile what's left after the parse (Peterson 0.7 s, biscayne 1.6 s):
   ingress conversion and structuring.
2. Optional: let `WORD_LINES` take lines with quotes or trailing comments.
   No large corpus file seems to need it.
3. Remaining parse time is mostly array runs plus Lark's per-line
   overhead; look at it only if the profile points there.
4. Unchanged: re-check CI time of `test1002_biscqtg*`; `adapters.py`
   recarrays and codegen types stay deferred.

Gotcha: in zsh, `$D` with several sim dirs isn't word-split, so `vs3.py $D`
passes one path (only the last name prints). List the dirs out.

### Done (2026-10-15, night) -- pushed to the fork at 10a8d23e

Profiled after the parse (Next #1 above). Commits (all pushed:
fa5103ba..10a8d23e on wpbonelli/pyphoenix-project item-table):

- **2acf0b6b `perf(reader): possessive NUMBER_LINES`**. The lexer is
  still most of the parse, and nearly all of it is `NUMBER_LINES` scanning
  array data (~7.5 ms/MB; Peterson 78 MB, biscayne 67 MB). Every quantifier
  in the number pattern is now possessive. Equivalent because a number is
  always followed by a separator or newline, which no number character
  is, so backtracking can't find another match. A linear scan over every
  Peterson/biscayne file found the same 224 runs at the same spans; tricky
  single lines (`1.`, `.5`, `.`, `1e`, `1e5x`, `1.2.3`, `-1.d-3`, ...)
  agree. Regex time 1.45 s -> 0.98 s. Also tried: a lookahead form without
  the alternation (1.19 s, slower). A character-class-only scan is 5x
  faster but takes bad numbers (`1.2.3`), so it's rejected. `WORD_LINES`'
  number lookahead is left as is (few lines).
- **10a8d23e `perf(item-table): share a missing column's plain default`**.
  `ItemTable.values` built a column the rows didn't set with a `_default`
  call per row: biscayne.riv's `aux`, 1.27M rows, via `package._lengths`
  in `_set_dims_from_counts`, ~0.3 s profiled. Now, unless the default is
  an `attrs.Factory` (a row's own object), it's `[default] * n`.
- Checked and not worth it: array reads (`run_values`). `np.fromstring(sep="
  ")` is no faster than `np.array(text.split(), dtype=float)` (both ~0.03
  s per 500k values); it's float parsing.

Verification: basic digests 0 differences vs `dig_head.pkl`; typed 0
differences vs `td_head.pkl`, errors 6/6; codec, reader, grammar_gen and
period_lists tests pass.

| model        | before (parse) | now (parse)   | flopy3 |
|--------------|----------------|---------------|--------|
| Peterson     | 1.41 s (0.70)  | 1.25 s (0.57) | 2.92 s |
| biscqtg_disv | 2.62 s (~1.0)  | 2.23 s (0.76) | 9.05 s |
| secp         | 0.98 s (0.61)  | ~0.95 s (0.44)| 2.5 s  |

(Whichever sim is first in a `vs3.py` run also pays the component
imports, ~0.2 s warm.)

Next (deferred 2026-10-15: optimization paused here; next step is a PR description for everything on item-table):

1. **Per-row Items in `Item.from_rows`**, the biggest cost after the parse:
   - DISV `CELL2D`, 106k rows: ~1.0 s profiled (`read_row` 0.56, `Cell2d`
     init 0.35, `_file_array` 0.30, `NumberRows.rows` 0.26);
   - Peterson SFR period data, 52k rows (41.8k period + 10.5k
     connectiondata): ~0.47 s profiled.

   These miss `read_table` (column-wise). Probably `CELL2D`'s
   variable-length `icvert` and SFR's keyword/union rows, but **unconfirmed**:
   check `_parse_rows`'s routing first. Then either teach `read_table`
   those shapes or make the per-row path cheaper.
2. Still: optional `WORD_LINES` quotes and comments; CI recheck;
   `adapters.py`; codegen types.

Scratch: `runs/lexfile.py <simdir>` gives per-file parse time and the
size of each terminal's tokens (it skips files that don't parse, like
external arrays). `runs/rebench2.py <files>` gives a linear-scan timing
of the regex variants plus the equivalence cases. Profiles:
`runs/peterson4.prof` and `runs/bisc6.prof`. Digests: `dig_poss.pkl`,
`dig_def.pkl`, `td_poss.pkl`. Note that `digest.py` takes
`<out.pkl> <corpus dir>`.

### Profiled after the parse (2026-10-16)

On `item-table` at `4f0c2929` (local commit, not pushed; the previous
"Next" list is superseded by this one). Wall time per phase, from timers
wrapped around the hot functions rather than cProfile, which roughly
doubles per-row code (`scratchpad/runs/phases.py <simdir> [runs]`). Most
of what's left after the parse is turning text into numbers. The
structuring logic itself costs less than expected.

biscqtg_disv, 2.25 s:

| phase                                                    | time   |
|----------------------------------------------------------|--------|
| Lark parse                                               | 0.76 s |
| RIV `read_table`, 100 periods, 1.27M rows, 57 MB         | 0.69 s (`np.fromstring` 0.48, `_widths` 0.08) |
| DISV `cell2d`, 106k rows 9–13 values wide                | 0.53 s |
| `_set_child_parents`, mostly walking `cell2d` rows       | 0.09 s |
| everything else (vertices, WEL, ...)                     | ~0.1 s |

`cell2d` alone (`runs/c2d.py <simdir>`): `NumberRows.rows` 0.16 s,
`_plan` + `read_row` 0.22 s, `Cell2d(**kwargs)` 0.17 s. Its widths:
83,648 rows of 9, 16,315 of 10, 6,042 of 11, 240 of 12, 12 of 13. It's
ragged, so it misses `read_table`, and `_plannable` is False (an
`ncvert` count column), so it's a list of Items, not an `ItemTable`.

Peterson, 1.2 s:

| phase                                                 | time    |
|-------------------------------------------------------|---------|
| Lark parse                                            | 0.53 s  |
| internal arrays (`row_values`, 10 runs, 76 MB)        | 0.30 s  |
| component imports (once per process)                  | 0.15 s  |
| SFR period rows (per-row union reads, `_check_keyword`) | 0.14 s |
| `_check_lookup_counts` (SFR connectiondata `ic`)      | 0.055 s |
| `_set_child_parents` (`_row_children` on SFR rows)    | 0.045 s |
| SFR connectiondata + packagedata rows                 | 0.04 s  |

Number readers, benchmarked on the same text (`runs/numread.py`,
`numread2.py`, `arrread.py`):

| reader                                         | RIV, 57 MB | Peterson arrays, 76 MB |
|------------------------------------------------|------------|------------------------|
| `_widths` + `np.fromstring(sep=" ")` (current for tables) | 0.59 s |                  |
| `np.fromstring(sep=" ")` alone                 | 0.48 s     | 0.38 s                 |
| `np.array(text.split(), dtype=float)` (current for arrays) |  | 0.29 s              |
| `np.loadtxt(StringIO(text), ndmin=2)`          | 0.29 s     | n/a (ragged lines)     |
| `np.loadtxt`, `comments=("#", "!")`            | 0.48 s     |                        |
| `pd.read_csv(sep=r"\s+", engine="c")`          | 0.23 s     |                        |
| `pd.read_csv(..., float_precision="round_trip")` | 0.67 s   |                        |

`loadtxt` gave the same values as `fromstring` bit for bit. Pandas
matched on this file too, but its default parser can round off by a
unit in the last place, and round-trip parsing is slower than we have
now, so it's rejected. Array reads (`row_values`) are already at the
float-parsing limit, as found before.

Plan, by size:

1. **`read_table` reads with `np.loadtxt`** instead of `_widths` +
   `np.fromstring`. RIV 0.59 s -> 0.29 s (about 0.3 s off biscqtg).
   `loadtxt` raises ValueError on a row of another width or a value
   that isn't a number, which replaces the `_widths` check: catch it
   and return None. Check the result has `len(first)` columns. Keep
   `without_comments` (cheap when there are no comments) rather than
   `comments=`, which is slower. Commas and `D` exponents are already
   fixed by `NumberRows.text`.
2. **Ragged numeric blocks by column, one width group at a time**
   (`cell2d`). Prototype `runs/ragged.py <simdir>`: 0.53 s -> 0.33 s,
   giving equal Items. For each width: lay out its first row with
   `_spans`, build the columns as `read_table` does (`_column`), check
   that each count column (`ncvert`) equals its array span's width
   (`_sized_by_field`), else fall back. Then `ItemTable(...).to_items()`
   per group, placed back in row order. Parse the text once: the
   prototype splits it twice. Then about 0.18 s is left, nearly all the
   106k `Cell2d` inits (an `on_setattr` hook for `icvert` and the
   count check in `Item.__attrs_post_init__`). Two ways past it:
   - build them like `item_table._plain` (`object.__new__` +
     `object.__setattr__`), skipping converters and validators, which is
     safe only for values read by column, already typed;
   - store `cell2d` as an `ItemTable` with `icvert` as an object column
     of tuples (`_fit` already falls back to objects), which means
     relaxing `_plannable` for count columns. No Items at all, but a
     semantic change: rows become views.
3. **Skip the per-row child walk for rows that can't hold children.**
   `_set_child_parents` and the children property (component.py ~365)
   call `_row_children` on every row, about 227k times for biscqtg.
   `_may_hold_children` is cached per class, so check it once per field
   (the list's item type) before iterating. About 0.1 s off biscqtg,
   0.05 s off Peterson. For SFR, whose union arm may hold a TAB6 child,
   also precompute which fields to look in, rather than `getattr` and
   `attrs.has` on every field of every row.
4. **Smaller:**
   - `_check_lookup_counts` builds lambdas and calls `dim_value` for
     every SFR connectiondata row: compute the expected counts by
     column once (about 0.05 s);
   - SFR period rows check their arm's keyword per row, which is mostly
     unavoidable;
   - component imports, 0.15 s once per process, are out of scope.

5. **Slots on Items (memory, not speed).** The generated item classes
   are `@attrs.define` (slotted), but their plain bases `Record`
   (record.py:179) and `Item` (item.py:926) have no `__slots__`, so
   every instance still has a `__dict__`, and the slots save nothing.
   Tried `__slots__ = ()` on both: a `Cell2d` init stays at 1.22 µs, while
   memory for 100k of them drops from 12.0 MB to 8.8 MB
   (`runs/slotbench.py`). biscqtg and Peterson load in the same time, and
   `test_mf6_period_lists.py` passes (45). Do it, first of all the steps:
   it's two lines and a quarter less memory for every row of every list
   that isn't an `ItemTable` (more as the rows get smaller). First grep for anything
   setting a non-field attribute on an Item or Record, or reading its
   `__dict__` (none in item.py, record.py or item_table.py). `ItemTable`'s
   views (`_view_class`) declare `__slots__ = ("_table", "_i")` but still
   get a `__dict__` from the same bases; this fixes that too.

   Components (`Package`, `Model`, ..., `slots=False`) don't need slots:
   a simulation has tens of them. They read and write their own
   `__dict__` in about 30 places (package.py, component.py, model.py,
   period_lists.py), mostly without needing to:
   - `c.__dict__["_parent"] = self` (component.py 394–559): `_parent` is
     a plain attrs field with no `on_setattr`, so `c._parent = self` does
     the same;
   - writes of a field's own value (package.py 396, 573, 605–613):
     these skip the field's `on_setattr` hooks (convert, validate,
     `_coerce_rows`, `_check_dim`), which is deliberate, but
     `object.__setattr__` is the usual way to do that, and
     `_init_item_lists` already uses it;
   - reads, `self.__dict__.get(f.name)` (package.py ~10 places,
     period_lists.py 326): every field is set by the time these run, so
     `getattr(self, f.name)` should give the same value. Check each one,
     though: a read during init, or a property shadowing a field, would
     behave differently;
   - `Model.workspace`: a property overriding `Context`'s `workspace`
     field, its value kept in a non-field attribute `_workspace`. This one
     really needs `__dict__` (or its own attribute).

   Clean these up along with the structuring simplification. They aren't
   a speed or memory issue.

1–3 bring biscqtg to about 1.6 s. After that, the parse is the larger
half: `NUMBERS`' regex alone is 0.67 s of it.

On simplifying: rows reach Items three ways: `read_table` (by column),
`_plan`/`read_row` (by row, per width) and `from_tokens` (`_solve`,
the fallback). With step 2 generalized, every block of only numbers
would be read by column, ragged or not, and by-row reading would be
left for rows with words (SFR's). That's the natural place to simplify
`_parse_rows` / `from_rows` while doing the speedups.

Verify each step with the load snapshots (step 0), then
`test_mf6_period_lists.py`, the item-table and reader tests, and the
large loads of biscqtg and Peterson by test ID (targeted tests only, no
full smoke run). Re-time with `runs/phases.py`.

### Step 0: load snapshots, before any of the above

Work is on branch `load-perf`, cut from `origin/develop` at `6b233ddb`
(#479, squash-merged from `2c79a17f`). The unmerged
`4f0c2929` (reassigned list rows) is cherry-picked onto it as
`00e1aef0`. Its tree is identical to `4f0c2929`'s.

`runs/digest.py` already pins load results: it hashes every package
field of every corpus sim, and `runs/digcmp.py` diffs two digests. Make
it a test with devtools' `snapshot` fixture (syrupy;
https://modflow-devtools.readthedocs.io/en/latest/md/snapshots.html).
That's better than a CI job that compares the PR against its base
branch:

- intended changes show in the PR diff as changed snapshot entries,
  accepted with `pytest --snapshot-update`;
- it runs locally in the normal suite, with no second checkout;
- it catches drift from dependency upgrades (numpy, xarray, attrs),
  which a base-branch comparison misses since both sides share the
  environment. devtools also warns on a numpy major change.

Shape:

- In `test_mf6_load_all_models.py`, for each known-passing model,
  `assert load_digest(sim) == snapshot`. Use syrupy's default (amber,
  readable) format, not devtools' array extensions: those store whole
  arrays (Peterson has a 76 MB one; ~242 models would bloat the repo).
  An entry is a nested dict, package → field → `(dtype, shape, sha1)`
  or a repr, so a failure names the field, like `digcmp.py`.
- Harden the digest into a test helper first:
  - cast ints to int64 and floats to float64 before hashing (the
    default int dtype is platform-dependent under numpy 1.x);
  - include xarray dims and coords, not just values;
  - no reprs with memory addresses (`object at 0x…`): fail loudly on
    one, rather than snapshot it;
  - decide whether public attrs fields per package are enough, or
    children's state too.
- Add `syrupy` to the test/dev pixi features. devtools' snapshots
  module raises ImportError without it; it isn't installed yet.
- Caveats: float bits should match across OSes (correctly rounded
  parsing), but the first matrix run confirms it. A models-registry
  update changes the snapshots of the fixtures it touches; that's a
  true failure but noise in an unrelated PR, so consider pinning the
  registry ref.

As built (branch `load-snapshots`, from `load-perf`, which is pushed
for its own PR):

- One JSON file per model (syrupy's `JSONSnapshotExtension`), not one
  amber file: no xdist write contention on `--snapshot-update`, and a
  diff stays local to its model. ~5-15 KB each.
- Every component's fields, sim and models too, private ones as well:
  period data is in `_stress_period_data`, which the scratch digest
  skipped. Only `_parent` and `write_context` are left out, and fields
  that are None.
- Canonical, so representation changes don't churn: an ItemTable and a
  list of one attrs class' instances digest the same (by field, from
  row values); numeric lists and arrays as `<i8`/`<f8`/bool hashes;
  numpy scalars as Python ones; floats by repr; the workspace path
  replaced. Long values collapse to `N chars <sha1>` (200 chars for
  plain values, 4000 with nested tables/records).
- No xarray values turned up among loaded fields, so nothing for dims.
- syrupy warns "Can not relate snapshot location" on writes, since the
  param IDs have slashes; harmless (subset updates don't delete other
  snapshots).

Status (2026-10-16, branch `load-snapshots`, local only): done, one
commit each. Step 0 `cb9716f4`, 5 `2e034411` (slots only; the component
`__dict__` cleanup is left for the simplification), 1 `8b8d6110`
(read_table 0.72 -> 0.36 s), 3 `7bcdbcb3`, 2 `54f0ec86` (`read_ragged`;
cell2d 0.64 -> 0.40 s, still via `to_items`, neither of the two ways
past the inits taken), 4 `ff6765a1` (`_check_lookup_counts` only), mypy
`6434653d`. biscqtg_disv 2.34 -> ~1.7 s; Peterson ~1.2 s, about the
same. Snapshots unchanged throughout. `load-perf` got `8988eaae` (mypy)
after this branch was cut; rebase onto develop once it merges.

Order: harden the helper, generate snapshots on `load-perf` before any
perf change, commit, then use the snapshot test as each step's
`differences: 0` check (instead of the scratch pickles). Then step 5
(slots), 1, 3, 2, 4. Commit each separately.

## Memory (profiled 2026-10-16)

Work is on branch `load-memory`, worktree
`.claude/worktrees/load-memory`, cut from `load-snapshots` at
`86da2ba3`. Nothing is pushed.

[`io-benchmark-results.md`](io-benchmark-results.md) reports peak RSS. On biscqtg that's 1161 MB
for flopy4 vs 596 MB for flopy3. **On macOS, RSS overstates the gap.**
Pages that malloc has freed but the OS hasn't reclaimed still count
toward RSS (and `ru_maxrss`). fp4 frees several big transient buffers
during a load, so its RSS stays high: after `del sim`, RSS is 915 MB and
the footprint is 268 MB. Measure `phys_footprint` instead, read through
`proc_pid_rusage` (what Activity Monitor shows). Linux glibc returns
large freed blocks to the OS, so RSS there should track the footprint
more closely. Not checked.

None of the plan's earlier items explain the gap. All of `cell2d`'s
Items, the lists of tuples included, come to about 44 MB.

### Footprint per phase (MB)

Each library ran in its own process, with a warm-up load of
`test001b_Tlogarithmic` first. Each "+" is the footprint change for
that phase.

| phase | biscqtg fp3 | biscqtg fp4 | Peterson fp3 | Peterson fp4 | secp fp3 | secp fp4 |
|---|---:|---:|---:|---:|---:|---:|
| import + warm-up | 128 | 218 | 125 | 222 | 125 | 222 |
| load | +223 | +283 | +113 | +29 | +69 | +63 |
| fp3 data access (`get_data`, kept) | +172 | n/a | +41 | n/a | +34 | n/a |
| peak footprint (whole run) | 552 | 775 | 310 | 312 | 280 | 345 |
| peak RSS (for comparison) | 721 | 1215 | 530 | 697 | 380 | 613 |

- **Load:** fp4's model is no larger than fp3's once fp3 has read its
  data. On biscqtg, fp4's load has no transient above what it keeps
  (tracemalloc: 300 MB current, 300.8 MB peak).
- **Write:** on biscqtg, fp4 peaks 257–283 MB above the loaded state;
  fp3 peaks about 30 MB above it.
- **Peterson:** fp4 keeps only +29 MB, which seems small for 76 MB of
  INTERNAL array text. Not investigated.

### Causes, and fixes in order

**M1. Write builds every list row as Python objects at once.** About
+270 MB of peak on biscqtg. `_rows_to_tuples`
(`converter/egress/unstructure.py:138`) calls `ItemTable.tokens()`
(`item_table.py:305`), which turns all 100 RIV periods into tuples of
Python numbers (1.27M tuples, about 6.3M boxed values) in
`_unstructure_package` (`unstructure.py:269`, `spd_period`) before any
of it is written. The peak is in `filters.py:343` `data2lines`, called
from `macros.jinja:186`. Fix: stream instead. Hand the template one
period's rows at a time (a generator, or keep the `ItemTable` and
convert in the filter), or format a table's columns to text with numpy
and skip the tuples altogether. Same output; check it with the write
and roundtrip tests. This is also likely the bulk of biscqtg's 3.1 s
write.

**M2. Eager imports of interop code.** +90 MB and about 1.3 s, on every
model. flopy4's own modules add about 4 MB. The rest is:
- flopy3: +36 MB, 0.47 s;
- xugrid: +14 MB, 0.8 s cumulative, pulling in numba (+21 MB) and dask
  (+17 MB).

They're imported at the top of `flopy4/adapters.py` (xugrid, flopy
StructuredGrid), `flopy4/mf6/adapters.py` (flopy datbase, Grid,
ModelTime), `mf6/gwf_methods.py` (xugrid) and
`mf6/{dis,disv,disu,model}_methods.py` (flopy discretization). Fix:
import them inside the functions that use them, or behind a lazy module
attribute. Check that nothing at module level (base classes, type
annotations evaluated at runtime) needs them. Target:
`import flopy4.mf6.simulation` without `flopy`, `xugrid`, `numba` or
`dask` in `sys.modules`. A test can assert that.

**M3. CONSTANT period arrays expanded.** 171 MB kept on biscqtg.
`_read_control_record` (`structure.py:290`) returns
`np.full(length, v)` for CONSTANT, and READARRAY period blocks
(`_parse_readarray_period_block`, `structure.py:551`) call it once per
period. biscqtg's RCH (100 periods) and EVT (101) are all
`CONSTANT x`, giving 201 × 106,257 float64s from about 2.4 KB of input.
flopy3 keeps constants as constants. Options:
- store the scalar. The writer must then emit CONSTANT, and every
  reader of the field (`to_xarray`, period lists, adapters) must
  broadcast it;
- store `np.broadcast_to(np.float64(v), (length,))`. No copy, and
  everything that reads it still works, but it's read-only, so in-place
  edits (`pkg.recharge[1][5] = ...`) raise. That needs copy-on-write or
  a documented limit.

Decide which before starting. This changes how the values are stored,
so check that load snapshots stay equal (they digest values, so they
should). The writer could also stop writing a full array as INTERNAL
when it's really a constant (`external.py` already does
`nanmin`/`nanmax`/`array_equal` on each array).

**M4. `_disambiguate_ga_variant` reads whole files.**
`structure.py:577` does `path.read_text().upper()` on every file whose
ftype has a G/A variant, just to find `READASARRAYS` or
`READARRAYGRID`. For biscqtg's RIV that's about 114 MB of temporary
strings, read before the real parse reads the file again. The memory is
transient, so it mostly shows in macOS RSS, but it's also a wasted
57 MB read. Fix: read lines only until `END OPTIONS`.

Estimate: M1–M3 bring biscqtg's peak footprint from 775 MB to about
250 MB (flopy3: 552). Rough, not measured.

Order: M1, M2 (no behavior change), then M4 (small), then M3 once the
storage question is settled. Commit each separately. Check each against
the load snapshots and the write/roundtrip tests, and re-measure with
`phases.py`.

### Done (2026-10-16) -- branch `load-memory`

All four are in, a commit each, on top of `load-snapshots` (`86da2ba3`):

- **M1** `4f68fe76`: `unstructure` gives a block's list rows as a lazy
  `Rows` sequence (`converter/egress/unstructure.py`), whose tuples are
  made per block as the template iterates. JSON/TOML writes `materialize`
  them first. `field_type` and `data2list` accept any `Sequence`. The write
  peak above the loaded model fell from about +270 MB to 0–45 MB. Write
  time didn't change (about 3.0 s on biscqtg), so the tuples weren't the
  write's cost. That's a separate item if write speed matters.
- **M2** `c9bb7ac2`:
  - `flopy4.mf6.utils` loads its modules on first use (module
    `__getattr__`).
  - The dis/disv/disu/tdis/model/GWF/simulation methods and `NetCDFModel`
    import flopy and xugrid inside the methods that use them, with
    annotations under `TYPE_CHECKING`.
  - The `coerce` hooks and `_wrap_array` check against flopy's and dask's
    classes with `flopy4._imports.isinstance_of`, which doesn't import
    the module. A value can't be an instance of a class from a module
    that was never imported.
  - Import time fell from about 2.1 s to 0.8 s. `test/test_imports.py`
    checks that build, write and load import none of flopy, xugrid,
    numba, dask, matplotlib, shapely or pyproj.
  - Still loaded at import: pandas and scipy, from xarray itself, and
    pooch, from `modflow_devtools.dfns`. Those come from dependencies,
    not from this repo.
- **M4** `e312c66a`: `_disambiguate_ga_variant` reads lines only up to the
  end of OPTIONS (or the first other block). On biscqtg's RIV file that's
  0.2 ms and no allocation, down from 49 ms and 114 MB.
- **M3** `2862cf91`: we chose the 0-d array.
  - `_parse_readarray_period_block` keeps a non-layered CONSTANT as
    `np.asarray(v)`, as construction already stores a scalar. Layered
    CONSTANTs and griddata are still expanded.
  - `dense()` takes a `shape`, which `period_shape(component, f)` in
    `package.py` resolves from the DFN shape. `period_array` and the
    NetCDF export pass it.
  - `attrs_xarray._period_dataarray` broadcasts a 0-d period to the shape
    of the periods given in full. That also fixes the existing failure
    when a constructed package mixed a scalar period with a full one.
  - `array_eq` treats a 0-d array as equal to an array holding its value
    everywhere.
  - Load snapshots were updated for 73 models. Only the shapes of the
    CONSTANT arrays changed (`float64[N]` to `float64[1]`), checked in the
    diff. The dense `period_array` values matched the base on all 207
    fields across the corpus.

Validation:
- Write output is byte-identical to `86da2ba3` on all 258 corpus models,
  checked after M1 and again after M3. The script is
  `scratchpad/mem/writeall.py`, with the base in a detached worktree at
  `scratchpad/base`.
- Smoke passed after M2. After M3, only the period-array tests, mypy and
  ruff were run locally; the full suite is left to CI.
- The worktree's own pixi env has no `mf6` binary, so locally the
  integration and output-reader tests need
  `PATH=<main>/.pixi/envs/dev/bin:$PATH`.

biscqtg footprint now (MB; single runs vary about ±50):

| | before | after | flopy3 |
|---|---:|---:|---:|
| import + warm-up | 218 | ~122 | 128 |
| kept after load | ~283 | ~125 | +223 (+395 with data read) |
| write peak above loaded | +257–283 | 0–45 | +30 |
| peak, whole run | 775 | 386–425 | 552 |

Left:
- The peak is now during the load, about 130 MB above what it keeps.
  Profiled below, under "Load peak".
- Peterson's small "kept" figure is still unexplained.
- Layered and griddata CONSTANTs are still expanded.

### Load peak (profiled 2026-10-16)

`scratchpad/mem/stages.py` patches `reader.load` and `structure_component`
and takes a tracemalloc timeline (with `reset_peak`) per file and stage.
The peak was in parsing, not in structuring. biscqtg's 57 MB
`biscayne.riv` was held four times over during the parse:

| Stage, biscayne.riv | Traced |
|---|---|
| `fp.read()` | +57 MB, briefly +114 MB (bytes and str together) |
| lark builds the tree | +114 MB: a `Token` is a `str` subclass that also keeps `.value`, so its text twice |
| transform the tree | +57 MB: `NumberRows(str(token))` copied again |
| structure Riv | the 71 MB it kept, plus the raw text still held |

Done, on `load-memory` (local, not pushed):
- `482f3600` perf(reader): the basic parser is built with
  `Lark(transformer=BasicTransformer())`, so callbacks run as it shifts
  and reduces, and no tree is held. `NUMBERS`/`RECORDS` use `token.value`.
  `_list` was removed: an inlined rule can't have a callback in this mode
  (lark fails in `parse_tree_builder`). The codec test that inspects
  tokens builds its own tree parser with `get_basic_parser()`. The parse
  of biscayne.riv went from 228 to 115 MB.
- `a7d5784d` perf(item_table): `read_table`'s columns were views into
  `loadtxt`'s whole matrix, so Riv also kept a float copy of its cellids.
  A column that shares memory with the matrix is copied. Riv keeps 51 MB,
  down from 71.

biscqtg traced: load peak 285 → 171 MB, kept 130 → 108 MB. Footprint
peak about 316–320 MB (was 386–425). Codec tests, 258 load snapshots
(unchanged), smoke, mypy and ruff pass. Load time unchanged (1.6–1.75 s).

What's held now, above the ~56 MB loaded before the `.riv`:

| Step | Held at once | Extra |
|---|---|---|
| `fp.read()` | the file's bytes and the decoded str | ~114 MB, briefly |
| `parse(data)` | the input str, plus the `NumberRows` text (each `token.value` is a slice, a copy) | ~114 MB |
| `structure_component` | the `NumberRows` text in `raw`, plus Riv's arrays (51 MB) | ~108 MB + temporaries |

The three are about the same height, so lowering one alone doesn't lower
the peak. Options:

1. **Read without the bytes.** `mmap` the file and decode from the mapping
   (`str(memoryview(mm), "utf-8")`, no bytes copy). Mapped pages are file
   cache, not heap. Read step ~114 → ~57.
2. **Free each period's text once structured.** Pass 3's loops keep every
   period's rows until the load returns, through `_raw` in `Package.load`,
   `raw` in `_load_mf6`, `raw_lower`, `kper_rows` and `rows`. The callers
   would hand `raw` over, and the loop would `kper_rows.pop(kper)` and
   drop the block from `raw_lower`. Structuring ~108 → ~60. Makes
   `structure_component` consume its input (opt-in if tests reuse `raw`).
3. Parsing still holds input and output, ~114:
   - **3a.** `NumberRows` holds (start, end) into the one decoded str.
     Parse ~57, but the str lives until structuring ends, so 2 frees
     nothing until then. Peak ≈ text + arrays, ~108. Small gain.
   - **3b.** Parse the mmap'd bytes with lark's `use_bytes=True`.
     `NumberRows` holds (start, end) into the mapping and decodes one
     period's slice when structuring asks. The file text never lives on
     the heap, so the peak is about what the load keeps plus one period.
     2 is then unnecessary for the number text. Unverified: whether lark's
     lexer takes an mmap; else read into `bytes` (57 MB, not doubled).

Chosen: 1 + 3b, prototyped on biscqtg before anything else.

Done (local, not pushed):
- `c0fee105` perf(reader): `reader.load` maps the file. The basic parser
  is built with `use_bytes=True`, and lexes the mapping through a
  `LexerThread` plugin (`from_custom_input`), since lark's `TextSlice`
  takes only `str`/`bytes`. `NumberRows` holds a `Span` (buffer, start,
  end, encoding), decoded when structured. The transformer gets the
  buffer from the `SOURCE` context var. `loads` parses its text's bytes.
  Files with `\r`, non-ASCII-compatible encodings, empty files and
  streams are read as text. The mapping is released with the parsed
  values (vmmap shows none after a load).
- `347406fe`: lark makes a bytes token's `str` its repr, which cost
  0.14 s on the 57 MB RIV (+10% load). A `ContextualLexer` plugin, whose
  `BasicLexer.match` returns NUMBERS as a `bytes` subclass with an empty
  `str`, removes it. A mapping costs a fixed ~4 ms per file on macOS (as
  much as reading 18 MB of text), so only files of 16 MB or more are
  mapped (`_MAP_SIZE`); 9 corpus files are.

biscqtg: traced load peak 171 → 116 MB (108 kept); footprint load peak
~320 → ~200–220 MB, and the run's peak is now the write's (232–258).
Load time unchanged (~1.55 s, alternating runs against `a7d5784d`).
Depends on two lark internals (`LexerThread.from_custom_input`,
`ContextualLexer.BasicLexer`); lark is pinned `<2`.

Also kept by the load, not yet addressed:
- Disv `cell2d` as 106k Items, about 44 MB of Python objects
  (`item_table.py` `read_ragged` → `to_items()`). Columns would be far
  smaller.
- Disv structuring holds about 28 MB transient above what it keeps.

### Tools

In `/private/tmp/claude-502/-Users-wbonelli-dev-pyphoenix-project/534761f2-da2c-4b52-aad7-86653208ceb8/scratchpad/mem/`:
- `footprint.py`: `footprint()` returns (current, lifetime-max,
  resident), in MB, via `proc_pid_rusage`.
- `phases.py {fp3,fp4} <model_dir> [warm_dir]`: RSS and footprint after
  each phase.
- `trace.py <model_dir> <warm_dir>`: tracemalloc around one fp4 load;
  prints what's kept, by line and by traceback.
- `sample_write.py <model_dir>`: samples the footprint against the
  main-thread stack during a write; prints the peak and its frames.
- `imports.py <mod>...`: footprint added by each import, in order.

Run them from the worktree with the main checkout's dev env, so the
worktree's `flopy4` comes first on the path:
`PYTHONPATH=$PWD /Users/wbonelli/dev/pyphoenix-project/.pixi/envs/dev/bin/python <script> ...`.
The models are copied in
`/private/tmp/claude-502/-Users-wbonelli-dev-pyphoenix-project/0c2187ab-eda9-4492-9ae6-11e169356e97/scratchpad/corpus/`
(e.g. `mf6__large__test1002_biscqtg_disv_dev`).

## Paused (2026-10-16): what remains

Optimization stops here. Where biscqtg stands, against where this plan
started:

| | start | now | flopy3 |
|---|---:|---:|---:|
| load time | 3.96 s | ~1.55 s | 8.84 s |
| big array file parse (RIV) | 32.8 s | ~0.6 s | |
| import | 2.1 s, 218 MB | 0.8 s, ~122 MB | 128 MB |
| kept after load | ~283 MB | ~125 MB | +223 MB |
| peak footprint, whole run | 775 MB | ~230–260 MB | 552 MB |

`load-memory` merged as #483 and was simplified in #484, so the "now"
column is develop at `8a3d3ac9` or later.

What remains, cheapest first:

1. **Profile the write.** biscqtg's write takes about 3.0 s, twice the
   load, and the run's peak footprint is now during the write. Its time
   was never profiled; M1 showed the row tuples aren't the cost. Likely
   suspects: per-value formatting in the Jinja filters (`filters.py`,
   `data2lines`) and `external.py`'s per-array `nanmin`/`nanmax`/
   `array_equal`. About half an hour to profile; any fix depends on what
   it finds.
2. **Disv `cell2d` as columns.** The largest item left in the load:
   about 0.5 s of biscqtg's 1.55 s (`NumberRows.rows`, `_plan` +
   `read_row`, `Cell2d(**kwargs)`) and about 44 MB kept as 106k Items,
   plus about 28 MB transient while structuring (Disv now peaks at
   93 MB, since its 9.4 MB file is under `_MAP_SIZE` and read as text).
   Rows are ragged (9–13 values) with an `ncvert` count column, so it
   misses `read_table` and `_plannable`. It's a storage and API change:
   users get `Cell2d` Items today. Needs its own plan: likely fixed
   columns plus a padded or offset-indexed `icvert`, with Items made on
   access. `_set_child_parents` (0.09 s, mostly walking these rows)
   shrinks with it.
3. **Layered and griddata CONSTANTs.** M3 kept only non-layered period
   CONSTANTs as 0-d arrays; layered ones and griddata are still
   expanded. Needs a decision on how a per-layer constant is stored
   (e.g. one 0-d array per layer, broadcast by `dense()`), and touches
   the same readers M3 did (`to_xarray`, period lists, adapters, NetCDF
   export, the writer).
4. **Typed reader: mixed/ragged list rows** (Peterson `v6.sfr`, basic
   0.70 s vs typed 2.07 s). Only matters if the typed reader becomes the
   default (see [`typed-loader-wiring.md`](typed-loader-wiring.md)). Either a run terminal that allows words, or splitting such
   rows as text in the transformer, as `NumberRows` does.
5. **Smaller or speculative:**
   - Peterson SFR per-row Items (~0.47 s profiled, 52k rows); check
     `_parse_rows`'s routing before assuming why it misses `read_table`.
   - Peterson's small "kept" footprint is unexplained.
   - Deferring OPEN/CLOSE reads until access, as flopy3 does. Doesn't
     help Peterson (only its DIS is external).
   - CI time of `test1002_biscqtg*` cases; decide whether the test-side
     trim ("Test-side" above) is still worth it.
   - Number-like text (an obsname `1.50` reloading as `1.5`): the basic
     transformer still converts tokens before the schema is known. Tracked
     as item 2 of [`followups-after-row-layout.md`](followups-after-row-layout.md); a fix touches the same conversion
     point #484 consolidated.
   - Still deferred: `adapters.py` recarrays, codegen types, optional
     `WORD_LINES` quotes and comments.

Watch: the mapped read depends on two lark internals
(`LexerThread.from_custom_input`, `ContextualLexer.BasicLexer`). lark is
pinned `<2`; the `test_load_file_*` tests in `test_mf6_codec.py` would
catch a break when it's bumped.

## Validating

- **Equivalence.** Before changing anything, dump the outputs for a
  sample of corpus files and diff against them after each change.
  For approach 1, dump `loads_basic` (and `loads_typed` for the typed
  step); for the others, dump `loads_typed`. Include `biscayne.riv`,
  `secp_mf6.npf`, a Keating `.disu`, a file with comma-separated data
  (TDIS `1.00000000,1,1.00000000`), one with `D` exponents, and one with
  remarks or comments on data lines. Speedups must not change any output,
  including int vs float.
- **Correctness.** `test_load_simulation`
  (`test/mf6/test_mf6_load_all_models.py`) loads the corpus through basic
  and runs the typed check (`_check_typed_grammar`) on known-passing
  models. Run it on the non-large models for quick iteration:
  `pixi run -e dev pytest -n auto test/mf6/test_mf6_load_all_models.py -m "not slow"`.
  Then run a few large ones (secp, Peterson, one biscqtg) directly by
  test ID. Also run `test/mf6/test_mf6_grammar_gen.py` (grammar text
  assertions, which need updating if `typed.lark` changes), the
  reader/transformer unit tests, and the smoke tests.
- **Speed.** Benchmark on `biscayne.riv` (list rows), `secp_mf6.npf`
  (INTERNAL arrays) and `biscayne.disv` (vertex/cell lists), with the
  parser built first so construction isn't timed.

Benchmark script. Run it from the repo root with
`pixi run -e dev python <script>`:

```python
import tempfile, time
from pathlib import Path

from modflow_devtools.models import copy_to

from flopy4.mf6.codec.reader import (
    BASIC_PARSER, BASIC_TRANSFORMER, get_typed_parser, get_typed_transformer,
)

cases = [
    ("mf6/large/test1002_biscqtg_disv_dev", "biscayne.riv", "gwf-riv"),
    ("mf6/large/test1002_biscqtg_disv_dev", "biscayne.disv", "gwf-disv"),
    ("mf6/large/test1005_secp", "secp_mf6.npf", "gwf-npf"),
]
for model, fname, dfn in cases:
    ws = copy_to(Path(tempfile.mkdtemp()), model, verbose=False)
    text = (ws / fname).read_text()
    print(f"{fname}: {len(text) / 1e6:.1f} MB")
    for name, parser, tx in [
        ("basic", BASIC_PARSER, BASIC_TRANSFORMER),
        ("typed", get_typed_parser(dfn), get_typed_transformer()),
    ]:
        t = time.perf_counter(); n = sum(1 for _ in parser.lex(text)); lex = time.perf_counter() - t
        t = time.perf_counter(); tree = parser.parse(text); parse = time.perf_counter() - t
        nodes = sum(1 for _ in tree.iter_subtrees())
        t = time.perf_counter(); tx.transform(tree); xf = time.perf_counter() - t
        print(f"  {name}: lex {lex:.1f}s ({n:,} tokens)  parse {parse:.1f}s  nodes {nodes:,}  transform {xf:.1f}s")
```

`parser.lex()` uses the standard (not contextual) lexer, so with a run
terminal its token count may differ from what the parser sees. Trust the
parse time. With approach 4 there's no separate tree, so time
`parser.parse(text)` end to end instead. `gwf-npf` is in
`KNOWN_TYPED_GAPS`, so typed may fail on `secp_mf6.npf`; skip typed for
it if so.

## Files

- `flopy4/mf6/codec/reader/grammar/basic.lark`: basic grammar (`_list`,
  `line`, `TOKEN`, `NUMBER_LINES` from #474, `WORD_LINES`).
- `flopy4/mf6/codec/reader/transformer/basic.py`: `BasicTransformer`
  (`line` :56, `TOKEN` and `_NUMBER`)
- `flopy4/mf6/converter/ingress/structure.py`: block-row consumers;
  `_read_open_close_values` (numpy precedent, :153),
  `_read_control_record` (:271), `_parse_array_block` (:324)
- `flopy4/mf6/codec/reader/grammar/typed.lark`: shared typed rules
  (`record`, `token`, `number`, `double`, `data`, `_data_line`)
- `flopy4/mf6/codec/reader/grammar/generated/*.lark`: checked-in
  generated grammars. Regenerate them after grammar-generator changes
  (see `flopy4/mf6/_sync.py`, `make_grammars`).
- `flopy4/mf6/codec/reader/transformer/typed.py`: `TypedTransformer`
  (`__getattr__` :49, `word`..`number` :184-200, `data` :202, `record`
  :220, `__default__` :302)
- `flopy4/mf6/codec/reader/grammar/names.py`: `parse_rule_name`
- `flopy4/mf6/codec/reader/parser.py`: parser construction (approach 4)
- `flopy4/mf6/codec/reader/__init__.py`: `loads_basic` / `loads_typed`,
  trim-and-retry
