# Should the typed grammar support trailing remarks at all?

**Archived 2026-10-19.** Answered: keep remarks. Removing them broke 357 more corpus files at negligible parse cost (see [`loader-roadmap.md`](loader-roadmap.md), "What we learned").

Raised 2026-09-18 during typed-reader-corpus review; not investigated further,
parking here for an issue.

## What a "remark" is

MF6 input lets almost any line end with free trailing text after its "real"
tokens -- not `#`-prefixed (that's `SH_COMMENT`, handled separately). E.g. a
CONSTANT line can read `CONSTANT 1.0  some free-text note`, or a record can
carry extra descriptive words after its real fields.

## How the two grammars handle it, and why that's asymmetric

`basic.lark` never models this explicitly: it's fully generic
(`line: item* _NL+`, `item: word | NUMBER`), so any trailing tokens are just
more items -- `structure.py` downstream knows how many tokens matter for a
given line and ignores the rest. No grammar-level concept of "remark"
needed.

`typed.lark` is field-shaped: every field/record/array/block rule has a fixed
arity, so an explicit `[_remark] _NL` had to be threaded onto nearly every
terminal rule to tolerate trailing free text without rejecting otherwise-valid
files. Call sites: `typed.lark:14,21-24,49` (layered/constant/internal/
external/timearrayseries/data/open_close_redirect), plus `macros.jinja`'s
`record_field`, `union_field`, `simple_field` (x2), `file_field`, `block_def`
-- 7 separate places.

## Why that single feature is a real complexity driver

Supporting a trailing remark forced:

- Newlines becoming significant (can't blanket `%ignore` them -- a remark
  needs a bound to stop at; see `typed.lark`'s header comment).
- A dedicated `COMMA` terminal excluded from `word`'s/`_REMARK`'s character
  class and `%ignore`'d separately, so a remark can't out-length a
  COMMA-separated data run with no surrounding spaces (confirmed against a
  real fixture: TDIS's `"1.00000000,1,1.00000000"` -- maximal munch always
  prefers the longer match regardless of priority).
- `WORD_STR`/`_REMARK` lexer-priority tricks (`typed.lark:34-41,44-52`) to
  keep numbers/keywords resolving correctly in states reachable from both a
  remark and a real field.

That single feature is also the direct cause of the one still-open real gap
in the typed grammar's corpus results: 2 `gwf-npf` files where a remark's
free text happens to contain a reserved word (e.g. a parenthetical comment
mentioning "constant"), and it loses to that word's keyword literal under
Lark's single-lexer priority rules. Fixing that specific case would need
per-context lexer modes, which Lark's LALR contextual lexer doesn't support.

## Open question for the issue

Is trailing-remark support actually load-bearing for the typed path -- i.e.
are there real corpus fixtures that fail to parse *without* it, or does every
real remark-bearing fixture happen to also be tolerated some cheaper way
(e.g. `basic.lark`'s free-form-item approach, or just not exercising the
field it would attach to)? If it's not load-bearing, dropping remark support
from the typed grammar would remove significant lexer complexity (7 grammar
call sites, the COMMA carve-out, and the two priority tricks) and the gwf-npf
gap along with it. If it is load-bearing, is there a lower-complexity way to
bound it than a dedicated lexer terminal threaded through every rule?

## Findings (2026-09-23)

Worktree `~/dev/pyphoenix-typed-remarks`. Branch `typed-remarks` (off
develop) has the reader benchmarks. `typed-no-remarks` stacks on top of it
and removes remark support: every `[_remark]`, `_REMARK`/`_remark`, and the
template import. The committed generated grammars get the same edit.

### Load-bearing: yes

Across all 2,228 corpus files, typed-parse failures go from 47 to 404: 357
newly fail and none newly pass. The 2 gwf-npf gap files still fail, since
their remark now has nowhere to go. Where the rejected remarks sit:

- ~90%: MF2005-style labels trailing an array control line --
  `CONSTANT 100.0 DELR` (146 dis files alone),
  `INTERNAL FACTOR 1.0 IPRN -1 Initial head for layer 1`,
  `OPEN/CLOSE f.top FACTOR 1.0 IPRN 5 top layer 1`.
- Option lines: `PRINT_INPUT (echo input to listing file)`,
  `SAVE_FLOWS flow15_flow.cbc`, `DEV_OMEGA 1D-5`.
- A few data rows: `0 0 0 ... row 1`.

### Performance: no parse-time case for dropping it

`pixi run -e dev bench --bench-manifest <file>` pins both variants to the
same 1,800 files, the ones the no-remark grammar still parses. Min of 3
rounds:

| stage | with remarks | without |
|---|---|---|
| parse-typed | 11.15 s | 11.63 s |
| loads-typed (parse + transform) | 15.24 s | 15.27 s |
| typed grammar build (30 components, one-time) | 1.71 s | 1.25 s |

The parse differences are within run-to-run noise: parse-basic moved 3-5%
between the runs on an unchanged grammar. The only measurable cost is +37%
grammar build, ~0.5 s once per process. The transformer never sees
remarks: Lark filters `_`-prefixed rules and terminals out of the tree, so
none of `transformer/typed.py`'s complexity or cost comes from them. The
typed loader's ~27% overhead vs. basic is in the transform, not the parse.

So the argument for dropping remarks is grammar/lexer complexity (plus the
2-file gwf-npf gap), not speed.

## Ideas for a cheaper remark

1. **One rest-of-line terminal, can't start numeric.** Replace the
   `_REMARK+` word run with a single token, roughly
   `_REMARK.-1: /(?![-+.\d,])[^\n]+/`.
   - Taking the whole remark as one token means no keyword inside it can
     win the lexer, so the gwf-npf reserved-word gap should close.
   - A remark can't start with a digit, sign, dot, or comma, so it can
     never swallow a comma-joined data run. The COMMA carve-out's
     remark-related reason goes away (COMMA may still be needed as a data
     separator).
   - Catch: after `CONSTANT 1.0`, a rest-of-line match beats `IPRN 5` by
     maximal munch. It needs a lookahead excluding the optional trailing
     keywords (`iprn`, `factor`, `(binary)`). That moves some complexity
     rather than removing it.
2. **Only allow remarks where the corpus has them.** Array control lines,
   scalar/keyword option lines, and data rows cover everything above.
   Record/union/file fields and block headers may not need them. Verify
   per site: re-add them one at a time and diff the failure set.
3. **Strip remarks before parsing.** A per-line preprocessing pass that
   knows each control line's arity (CONSTANT/INTERNAL/OPEN/CLOSE and their
   modifiers) and cuts the rest. That's cheap for array control lines,
   which are ~90% of the cases, but it's a second, non-grammar parser to
   keep in sync.
4. **Deprecate.** Keep today's grammar, warn when a remark is consumed
   (it's easy to count in a transformer if `_remark` becomes a named
   rule), and drop remarks in a later format version. Most real
   occurrences come from mf5to6-converted legacy fixtures.

The doc's claim that both priority tricks exist because of remarks is only
half right: `WORD_STR.-1`'s own comment traces it to LALR state merging
between `integer+` rules and a trailing `word`, not to remarks.
