# flopy4 development plan — Track A (input file loading)

**Archived 2026-10-19.** Done: Track A and Track B are both complete. The two open rows are resolved: the codec reader is off the legacy DFNs (#455), and namefile grammars are generated (`sim-nam.lark`, `*-nam.lark`). Using them is part of [`typed-loader-wiring.md`](../io/typed-loader-wiring.md).

Track B (remove `xattree`, issue #167) is done — see "Track B: closed
out" near the bottom. This file now tracks Track A only.

## Status snapshot (updated 2026-09-16)

**Track A was "largely done" as of the last snapshot (2026-09-10); the
two items that were still blocking are now both done too.** Six commits
landed since then: `743ecf1`/#350 ("make Simulation.load() work,
mostly"), `9192136`/#351, `034afa1`/#352, `f3cd6f6`/#353,
`e3075da`/#354 (the last two delete `overrides.py`/
`dfn_overrides.toml` entirely — the flopy4-side stopgap layer
[`dev3-migration-gaps.md`](dev3-migration-gaps.md) tracked is now gone, its upstream gaps fixed),
`5f1f4e2`/#355, and `67d0922`/#356 (Track B's xattree removal, which also
touched `structure.py`/`unstructure.py`). Of these, #350 is the one that
matters for Track A: it's what closed both previously-open items below.

| Piece | State |
|---|---|
| One field-metadata convention (`block=`), `dfn_type` gone | ✅ #339 |
| `Column`/`Schema` deleted; `Row` → then `Item`/`Record` refactor; `row.py` removed | ✅ #341, #348, #349 |
| Codegen on pydantic-native `modflow_devtools.dfns` dev3 schema | ✅ #348 |
| OC rtypes / union arms read from schema, not hardcoded tables | ✅ #348 |
| Generic structuring + binding resolution; `Simulation.load()`/`Gwf.load()` recurse, dims threaded from `dis` sibling | ✅ #348 |
| Typed union-item classes, top-level period unions (`item.py`, `dispatch_union_item`) | ✅ #349 |
| Flopy4-side DFN-override stopgap layer (`overrides.py`/`dfn_overrides.toml`) | ✅ deleted, #353/#354 — upstream devtools/mf6 fixes made it unnecessary |
| **Prove `Simulation.load()` end-to-end on real input** | ✅ #350 — see below, far exceeded original scope |
| **Close out PR #284** | ✅ closed (not merged) 2026-09-10; useful pieces salvaged into #350 |
| Codec reader path off legacy `modflow_devtools.dfn` | ❌ not started |
| Nested `ocsetting` union (OC) | ✅ done — [`nested-keystring-union-plan.md`](nested-keystring-union-plan.md) |
| Typed namefile grammar (Phase 3) | ❌ not started |

**Test state (reverified after the `ocsetting` change, same session):**
pixi `dev` env is green — `910 passed, 11 skipped, 4 xfailed` (908 base +
2 new tests). Three of the four xfails are the corpus-survey
fixture-quality gaps below (`test019_VilhelmsenLGR`, `_nr`,
`test060_gms_ets`); the fourth (`test_mf6_adapters.py::test_fails`) is an
intentional demonstration test, not a gap.

## Prove `Simulation.load()` end-to-end — done, exceeded scope

The original plan (2026-09-10 snapshot) called for running
`Simulation.load()` against `docs/examples/twri.py` and
`frenchman-flat.py`. What actually landed in #350 is stronger: a
**242-model corpus survey** against the real `modflow_devtools.models`
registry (`test/mf6/test_mf6_load_all_models.py`), not flopy4's own
hand-written examples. A first pass (2026-09-11) found ~9% loading
cleanly; a same-day debugging session (documented blow-by-blow in
[`load-corpus-gaps.md`](load-corpus-gaps.md), 13 numbered root causes, 11 fixed) took the pass
rate to **239/242 (98.8%)**, including the registry's own `test021_twri`
model — a real MF6 reference input, a stronger proof than the
hand-written `docs/examples/twri.py` would have been (which itself
remains an unexercised example script, not wired into any test). The
`_param()` helper in that test file marks every model not in
`KNOWN_PASSING` `xfail(strict=False)`, so a regression is a hard
failure and a newly-fixed model shows up as XPASS — the signal to
promote it.

The remaining 3 xfails are confirmed, documented, out-of-scope fixture
issues, not flopy4 bugs ([`load-corpus-gaps.md`](load-corpus-gaps.md) gaps #11-#12):
`test060_gms_ets`'s DFN fixture omits a field the current spec genuinely
requires; `test019_VilhelmsenLGR`(`_nr`)'s child model references an
external array file sized for the *parent* grid (26901 values into a
7020-shaped slot) — a stale/mismatched fixture pairing, confirmed by
reading the referenced file directly.

DIS-before-NPF/IC ordering and dims propagation (the two things the old
plan wanted separately confirmed) are implicitly exercised across this
entire corpus, not just a two-package case — no separate verification
needed. `test/test_package_load.py` (410 lines, also from #350) covers
package-level loading in more depth.

## Close out PR #284 — done

PR #284 ("input file loading") was closed, not merged, 2026-09-10 — the
right outcome per the original plan (its `structure.py` was superseded;
only the docs and the `FTYPES`/binding-resolution design were worth
keeping). #350's own description confirms the salvage: "this PR
salvages some docs and tests loading the examples and test models."
Concretely, `docs/dev/sdd.md`, `map.md`, and `test.md` were updated in
#350. [`on-representations.md`](on-representations.md) and [`typed-grammar-issues.md`](typed-grammar-issues.md) — the
other two files the original plan named — never existed outside the
closed PR #284 branch and weren't carried forward; nothing currently on
`develop` references them. No further action needed here.

## A3 — remaining, independent, non-blocking items

All three verified unstarted directly against current `develop` (no
progress since the 2026-09-10 snapshot, despite six intervening
commits — none of #351-#356 touched this scope):

- **Codec reader path off legacy `modflow_devtools.dfn`.** Confirmed via
  grep: `flopy4/mf6/spec.py`, `flopy4/mf6/codec/filters.py`,
  `flopy4/mf6/codec/reader/dfn2lark.py`,
  `flopy4/mf6/codec/reader/grammar/__init__.py`,
  `flopy4/mf6/codec/reader/grammar/filters.py`, and
  `flopy4/mf6/codec/reader/transformer/typed.py` all still import
  `modflow_devtools.dfn`/`modflow_devtools.dfn.schema` (the legacy flat
  schema), not `.dfns`. (`flopy4/cli.py` and two test files,
  `test_mf6_grammar_gen.py`/`test_mf6_reader.py`, also still use the
  legacy module — same migration would need to reach them too.) Same
  tree-walk conversion already done for codegen (`6cdfb2a`);
  `ComponentBase.get_block()` covers the block reverse-lookup. Own
  `schema_version` literal, no ordering dependency on anything else here.
- **Nested `ocsetting` union — done.** `OC`'s `Save`/`Print.ocsetting`
  (all 4 model families: gwf/gwt/gwe/prt) is now
  `Oc.All | Oc.First | Oc.Last | Oc.Frequency | Oc.Steps`, matching
  PRP's already-typed `releasesetting`. Full detail, including two design
  corrections found during review (a `top_level` flag so nested arms
  don't leak into the outer dispatch union; a dedup cache since
  `Save.ocsetting`/`Print.ocsetting` are independent-but-identical
  `Union` objects) in [`nested-keystring-union-plan.md`](nested-keystring-union-plan.md). Disclosed
  behavior change landed as planned: `ocsetting` is now required, no
  default; one downstream break found and fixed
  (`docs/examples/quickstart.py`'s `== ("ALL",)` comparison).
- **Typed namefile grammar** ([`mf6-object-model-plan.md`](mf6-object-model-plan.md) Phase 3).
  `basic.lark` still parses `packages`/`models`/`exchanges`/
  `solutiongroup` into generic rows — confirmed no `packages_record`-
  style typed rule exists anywhere in the grammar. Note:
  `get_typed_parser()`/`typed.lark` *do* exist and are exercised in
  `test_mf6_reader.py`, but for per-package block grammars (`gwf-ic`,
  `gwf-wel`, `gwf-oc`, `gwf-dis`, `gwf-npf`, `gwf-sto`) — an unrelated,
  already-landed mechanism, not the namefile-row typing this item is
  about. Porting PR #284's typed per-row grammar here is a
  validation/error-message improvement only, not a prerequisite for
  anything currently working.

No choreography needed between these three or against anything else —
all independent, land in any order, any time.

## Track B: closed out

`xattree` removal (issue #167's runtime-object-model half) merged into
`develop` via `67d0922` ("drop xattree (#356)", 2026-09-16). Verified
directly: zero `xattree` imports/decorator usage anywhere in source, no
`xattree` in `pyproject.toml`/`pixi.lock`, full suite green (908 passed).

What shipped: `flopy4/protocols.py` (`DatasetConvertible`/
`DataTreeConvertible`), `flopy4/mixins.py`, `flopy4/attrs_xarray.py` (the
generic attrs↔xarray conversion layer), explicit parent/child
attach/naming built directly into `flopy4/mf6/component.py`
(`_children`/`_parent`/`_resolve_child_name`/`_attach_to_parent_field`/
`_set_child_parents`), `@xattree` → `@attrs.define(kw_only=True,
slots=False)` on all 13 decorated classes, and `Component.pname`/
`Component.strict` deleted (both were workarounds the decorator's
removal made obsolete).

One deviation worth remembering: [`xattree-child-naming-plan.md`](xattree-child-naming-plan.md) had
scoped the child-naming consolidation as **upstream** work in the
`xattree` repo itself, gating flopy4's side on that fix landing and
being pulled in. That never happened — the equivalent logic was instead
built directly in `flopy4/mf6/component.py` as part of the final
cutover, which is why that plan is now superseded rather than completed
as written.

A follow-up pass (2026-09-16, same day) removed the loose ends the
xattree-era code/docs/tests still carried after the decorator itself was
gone: two dead functions in `flopy4/mf6/spec.py`
(`get_field_type`/`to_field`) that read a `"xattree"` metadata key
nothing sets anymore, and every remaining comment/docstring across
source, tests, and `docs/` that named "xattree" for historical
explanation rather than describing current behavior. Full suite
reverified green after that pass too.

Full design history: [`xattree-removal-plan.md`](xattree-removal-plan.md) (now a short "Final
status" note), [`protocols-plan.md`](protocols-plan.md) (dimension-resolution design, Phases
1-2 of which shipped as designed), [`xattree-child-naming-plan.md`](xattree-child-naming-plan.md) (now
superseded, per above).

## Housekeeping / loose ends

- The repo-root `*.md` plan files are untracked. Not versioning them per
  your call — but they're the design record this plan defers to, so keep
  them somewhere durable.
- [`nested-keystring-union-plan.md`](nested-keystring-union-plan.md) references `namefile-load-plan.md` and
  [`mf6-object-model-plan.md`](mf6-object-model-plan.md) interchangeably — same doc, two names in
  different comments (`filters.py:11` says `namefile-load-plan.md`). Pick
  one name if you touch it.
