# Typed grammar: trailing remarks and performance

Findings from 2026-09-23. There were two questions:

- Does the typed grammar (`flopy4/mf6/codec/reader/grammar/typed.lark` plus
  the generated per-component grammars) need to keep supporting trailing
  remarks, and what does supporting them cost?
- Why isn't the typed loader faster than the basic one, and what would make
  it faster? This is covered in
  [Why the typed loader isn't faster (yet)](#why-the-typed-loader-isnt-faster-yet).

## Background

MF6 input lets most lines end with free text after their real tokens, and it
isn't `#`-prefixed: `CONSTANT 100.0 DELR`. `basic.lark` never models this. Every
line is `item*`, and the structuring code downstream ignores the extra tokens.
`typed.lark` is field-shaped, so it threads an optional `[_remark]` through 7
rule sites (array control lines, data rows, scalar/record/union/file fields,
block headers). That forces:

- significant newlines, to bound the remark;
- a `COMMA` terminal that remarks can't contain, so a remark never swallows a
  comma-joined data run;
- a low-priority `_REMARK` terminal.

It also causes one known corpus gap: 2 `gwf-npf` files where a remark contains
a reserved word (e.g. "constant") that lexes as a keyword.

## Branches

- `typed-remarks` (off `develop`): opt-in reader benchmarks and this document.
- `typed-no-remarks` (on top of it): an experiment that removes remark support.
  It deletes every `[_remark]`, the `_REMARK`/`_remark` definitions and the
  template import, and makes the same textual edit to the committed generated
  grammars. That edit was checked against a scratch regeneration: only
  pre-existing DFN drift differs. **Not for merge.** It exists to measure
  things against.

## Remarks are load-bearing

The typed grammar was run over every package file of the 239 `KNOWN_PASSING`
corpus models (2,228 files):

| | failures |
|---|---|
| with remarks (`develop`) | 47 (exactly the `KNOWN_TYPED_GAPS` components) |
| without remarks | 404 |

357 files newly fail and none newly pass. The 2 `gwf-npf` gap files still
fail, because their remark has nowhere to go. The rejected remarks are:

- **~90%: labels trailing an array control line**, an MF2005-era convention
  that mf5to6-converted inputs carry over. Examples:
  - `CONSTANT 100.0 DELR` (146 `gwf-dis` files alone)
  - `INTERNAL FACTOR 1.0 IPRN -1 Initial head for layer 1`
  - `OPEN/CLOSE f.top FACTOR 1.0 IPRN 5 top layer 1`
- **Option lines**: `PRINT_INPUT (echo input to listing file)`,
  `SAVE_FLOWS flow15_flow.cbc`.
- **A few data rows**: `0 0 0 ... row 1`.

## Remarks cost (almost) nothing at runtime

Both variants were benchmarked on the same pinned 1,800 files (18.0 MB, 30
components). These are the files the no-remark grammar still parses. Figures
are the minimum of 3 rounds:

| stage | with remarks | without |
|---|---|---|
| typed parse | 11.15 s | 11.63 s |
| typed parse + transform | 15.24 s | 15.27 s |
| typed grammar build (30 components, once per process) | 1.71 s | 1.25 s |

The parse-stage differences are noise. `basic` parse, whose grammar is
unchanged, moved 3-5% between the same two runs. The one real cost is about
0.5 s of grammar construction per process. The transformer never sees
remarks, because Lark drops `_`-prefixed rules and terminals from the tree.

So the case for dropping remarks rests on grammar complexity and the 2-file
`gwf-npf` gap, not on speed.

Also: the claim that both lexer-priority tricks exist because of remarks
is only half right. `WORD_STR.-1`'s comment traces it to LALR state merging
between `integer+` rules and a trailing `word`. Only `_REMARK.-1` is
remark-specific.

## Options for a cheaper remark

1. **One rest-of-line terminal that can't start numeric**, roughly
   `/(?![-+.\d,])[^\n]+/`, instead of a run of word-like tokens.
   - The whole remark is one token, so a keyword inside it can't win. This
     should close the `gwf-npf` gap.
   - A remark can never start at a comma or number, which removes the
     remark-related reason for the `COMMA` carve-out.
   - Catch: after `CONSTANT 1.0`, a rest-of-line match beats the optional
     `IPRN 5` by maximal munch. It needs a lookahead excluding `iprn`,
     `factor` and `(binary)`, so some complexity moves rather than
     disappears.
2. **Allow remarks only where the corpus has them**: array control lines,
   option lines and data rows. Record/union/file fields and block headers may
   not need them. Verify each site by re-adding it and diffing the corpus
   failure set.
3. **Strip remarks before parsing**, with a per-line pass that knows each
   control line's arity. That's cheap for the ~90% on array control lines,
   but it's a second, non-grammar parser to keep in sync.
4. **Deprecate.** Keep today's grammar, count and warn when a remark is
   consumed (make `_remark` a named rule to see it in the transformer), and
   drop remarks in a later input-format version.

## Reproducing

```shell
# benchmarks (opt-in; ~4 min)
pixi run -e dev bench
pixi run -e dev bench --benchmark-compare          # vs. the last saved run

# A/B two grammar variants on identical input: write the manifest on the
# stricter variant first, then reuse it on the other
git switch typed-no-remarks
pixi run -e dev bench --bench-manifest /path/to/manifest.txt
git switch typed-remarks
pixi run -e dev bench --bench-manifest /path/to/manifest.txt --benchmark-compare
```

The corpus failure-set comparison used a scratch script that runs
`loads_typed` over `_collect_package_files` for every `KNOWN_PASSING` model,
with the `KNOWN_TYPED_GAPS` skip removed. That skip is the only difference
from `test_mf6_typed_grammar_corpus.py`.

## Why the typed loader isn't faster (yet)

The typed grammar had two main motivations:

- better error messages;
- speed, on the tentative reasoning that knowing field types lets logic
  move out of post-parse transformation (`structure.py`) and into the parser.

The first holds up. The second hasn't so far. The measurements below say
why, and point to a version of the idea that could work.

### Measurements

**End-to-end basic load (cProfile, whole corpus).** This is
`Simulation.load` over all 239 `KNOWN_PASSING` models:

| | cumulative time |
|---|---|
| total | 51.8 s |
| `loads_basic` (Lark lex + parse + tree + generic transform) | 45.2 s (~87%) |
| everything else in `structure.py` (`_parse_rows` 3.1 s, griddata 0.65 s, ...) | ~6 s at most |

cProfile inflates Python-heavy code, but the split is unambiguous. Almost
all load time goes to getting text through Lark. The structuring step the
typed transformer was meant to absorb is at most ~13%.

**Per-stage split on the five largest corpus files.** Best of 3; "floor" is
one compiled regex over the whole file plus `np.array(..., dtype=float)`:

| file | MB | basic lex / parse / transform | typed lex / parse / transform | tokens (both) | floor |
|---|---|---|---|---|---|
| `gwf_henry.ghb` | 2.29 | 0.61 / 0.82 / 0.22 | 0.47 / 1.57 / 0.79 | 239,751 | 0.061 |
| `model.disv` | 2.09 | 0.37 / 1.15 / 0.22 | 0.38 / 1.23 / 0.47 | 195,255 | 0.048 |
| `model.npf` | 1.63 | 0.34 / 0.42 / 0.22 | 0.52 / 0.57 / 0.17 | 99,450 | 0.056 |
| `keating.npf` | 0.97 | 0.24 / 0.25 / 0.07 | 0.16 / 0.19 / 0.08 | 65,385 | 0.021 |
| `keating.npf` (2nd model) | 0.97 | 0.13 / 0.20 / 0.07 | 0.15 / 0.41 / 0.07 | 65,384 | 0.023 |

Times are in seconds. Parse excludes lex, i.e. `parse() - lex()`.

**Whole-corpus baseline on `develop`.** `pixi run -e dev bench`, 2,149 files
(21.6 MB) both grammars parse, min of 3 rounds:

| stage | basic | typed | ratio |
|---|---|---|---|
| parse | 12.53 s | 13.45 s | 1.07x |
| parse + transform | 14.64 s | 18.53 s | 1.27x |

### Diagnosis

1. **The optimization targeted the wrong ~13%.** Moving structuring into
   the grammar could save at most the structuring time. Meanwhile ~87% goes
   to lexing and parsing in pure Python, which the typed grammar doesn't
   reduce.
2. **The typed grammar doesn't reduce per-token work; it adds to it.**
   - Both grammars produce identical token counts, and lexing costs about
     the same, since Lark's lexer is Python either way.
   - The typed grammar builds more tree per value: `double: SIGNED_NUMBER |
     NUMBER` creates a `Tree` node and a transformer callback for every
     number. That's why typed parse is ~2x basic on `gwf_henry.ghb`.
   - The typed transform builds an `np.array` from a Python list of floats
     and wraps each array in an `xr.DataArray`. It also routes most nodes
     through `__default__`, which does a `str.rsplit` and dict lookups per
     node.
3. **Grammar rules aren't cheaper than Python code.** In a pure-Python
   LALR parser, a rule is dispatched by the same interpreter that would run
   the equivalent post-processing, plus tree-node overhead. Moving logic
   into the grammar can clarify it, but only speeds it up if the move lets
   work be skipped entirely.
4. **The headroom is bulk numeric data, and neither loader uses it.**
   Almost all bytes in large files are array and list data. Getting the
   same numbers out in C (the "floor" column) is 10-30x faster than Lark's
   lexer alone, and ~50x faster than the full typed path. Any Python work
   per number, in the lexer, parser or transformer, is the ceiling.

### Is the principle valid?

- **Better errors: yes, and delivered.** A typed failure names the line and
  the tokens that were expected there. The cost is strictness: 357 corpus
  files fail once remarks are removed. MF6's own reader is lenient,
  line-oriented and keyword-driven, so a grammar stricter than the program
  it models will keep chasing fixtures. That's a design tension to manage,
  not a bug.
- **"Faster by moving logic into the parser": wrong as stated,** at least
  for a pure-Python parser (see diagnosis 3).
- **"Faster because type knowledge lets the parser avoid work": plausible,
  and untested.** The typed grammar knows:
  - where an array's data starts (after `INTERNAL`);
  - how many values it holds (from dims);
  - the dtype of each list column.

  That's enough to hand a whole data section to numpy as one token instead
  of lexing, parsing and transforming each number in Python.
  - Caveat: grabbing runs of numeric-only lines is mostly lexical, so the
    basic grammar could do much of it too.
  - Where typing uniquely helps: mixed-dtype list rows (int cellids, float
    values, a trailing boundname word), expected-size checks, and knowing
    what a data run means without a second pass.

Also not yet measured: a full typed load against a full basic load. Typed
`loads` output isn't wired into `structure.py`, so the benchmark stops at
`loads` for both.

### Ideas, cheapest first

**1. Lark's inline transformer, and grammar caching.**
- Passing `transformer=` to an LALR `Lark(...)` runs callbacks as each rule
  reduces, and never builds the tree. That targets exactly the tree cost
  separating typed parse (1.57 s) from basic (0.82 s) on `gwf_henry.ghb`.
- Things to check:
  - Inline mode dispatches by rule-name callbacks. Verify whether
    `__default__`, which the typed transformer relies on heavily, and
    token callbacks (`BasicTransformer.NUMBER`) are honored there. If not,
    the typed transformer needs explicit per-rule methods, or generated
    ones: the grammar is generated per component, so the callbacks could
    be too.
  - The transformer becomes bound to the parser. `get_typed_parser(name)`
    and `get_typed_transformer(name, dfn_path)` are cached separately
    today, so the parser cache would also need keying on `dfn_path`.
  - `__getattr__`'s `typed__` prefix delegation should still work, since
    inline lookup goes through `getattr`, but verify.
- `Lark(..., cache=True)` saves the analyzed grammar to disk, cutting the
  ~1.3-1.8 s per-process construction of the 30 corpus grammars to loading
  a cache file. It matters for CLI/short-lived use, not throughput. Also
  check whether `debug=True`, set on both loaders, costs anything outside
  development.
- Measure with `pixi run -e dev bench --benchmark-compare`; no manifest
  needed, since the grammar doesn't change.

**2. One token per numeric data block.**
- Add a terminal that matches a whole run of numeric lines, reachable only
  where the grammar expects array data (after an `INTERNAL` control line),
  and later list rows. For example, roughly:
  `DATA_BLOCK: /(?:[ \t]*[-+.\d][-+.\deEdD, \t]*(?:\n|$))+/`
- LALR's contextual lexer only offers terminals valid in the current
  state, so it shouldn't collide with `NUMBER` elsewhere. Confirm, since
  the grammar already hit a state-merging surprise (see `WORD_STR.-1`).
- In the transformer, parse it with `np.fromstring(block, sep=" ")`, or
  `np.array(block.split(), dtype=float)`, after normalizing commas and
  Fortran `D` exponents (`1.0D+00`). `flopy4.utils.parse_number` handles
  those per value today.
- Check the value count against the expected size from dims. That gives a
  better error ("expected 1000 values for STRT, got 999") than any
  token-level parse failure, which serves the error motivation too.
- Remarks: a trailing label on a data row ("`0 0 0 ... row 1`") ends the
  numeric run. Either let the block regex allow and strip an alphabetic
  tail per line, or end the block there and let the existing
  `_data_line ... [_remark] _NL` rule handle that line. The block regex is
  also a natural place to make remarks cheap, since it runs in C.
- List (period) blocks: rows mix int cellids, floats, and optional
  boundname/aux words. Options, roughly in order of effort:
  - a per-row regex built from the DFN's column dtypes;
  - `np.genfromtxt` or `pandas.read_csv(sep=r"\s+")` on the block text,
    both C parsers;
  - leave lists to Lark and do arrays only first, since arrays are most of
    the bytes in the largest files.
- The basic grammar could adopt the numeric-run terminal for arrays too.
  If it does, the comparison between loaders shifts from speed back to
  errors and structure.
- Validate on the corpus: `test_mf6_typed_grammar_corpus.py` for parse
  parity, the pinned benchmark for speed, and a value-level comparison
  against the current transformer output on a sample of files.

**3. Then decide what structuring belongs in the grammar.** With bulk data
out of Lark, grammar vs. transformer vs. `structure.py` is a question of
clarity and error quality, not speed. Wire typed `loads` output into
structure (or replace it), and add an end-to-end `Simulation.load` stage
to the benchmark, so both loaders are compared on the full path.

### How these numbers were produced

- The per-stage split used `parser.lex(text)` (materialized to a list) for
  lex, `parser.parse(text)` minus lex for parse, and `transformer.transform
  (tree)` for transform. The floor is `np.array(NUM.findall(text),
  dtype=float)` with `NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"`.
  That's a lower bound, not a correct parser: it ignores structure and
  would also pick up digits inside words.
- The end-to-end profile was cProfile around `Simulation.load` for every
  `KNOWN_PASSING` model, after one warm-up load.
- Both were scratch scripts, not committed. They're easy to reconstruct
  from the above.
