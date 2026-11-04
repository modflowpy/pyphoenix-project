# Road to MMP

What's left between today and the MMP, in what order, and what comes
after it. Written 2026-11-03 against `develop` (`8d25e4b7`). This doc
sequences the work and links to the plans that hold the detail, so it
stays short and the plans stay the source of truth. Update the status
column as things land. Every plan and design note, scheduled or not,
is listed in [plans/README.md](plans/README.md).

## Release shape

Decided 2026-11-03.

| stage | released from | installed by | gate |
|---|---|---|---|
| alphas | this repo | `pip install` from GitHub | as needed |
| betas, MMP the last of them | this repo | `pip install` from GitHub | "MMP gate" below |
| release candidates `flopy==4.0.0rcN` | flopy's `4.x` branch | PyPI, conda-forge | the integration plan's "Before the first release candidate" |
| GA | flopy, the last release candidate | PyPI, conda-forge | the integration plan's "Before GA" |

Why this order, and not integrating into flopy before MMP:

- **GitHub installs don't need the packaging work.** PyPI rejects git
  dependencies, `pip install git+...` doesn't. The devtools release, the
  xugrid range and Python 3.14 gate the release candidates, not MMP.
- **Testers can run both engines side by side.** `flopy4` and `flopy`
  are different packages, so testers can compare them on their own
  models in one environment.
- **Feedback lands at this repo's pace,** without flopy's review and CI
  on every beta fix.
- **The `4.x` branch stays short.** It's cut after MMP feedback has
  settled the API, so it carries a stable codebase, not beta churn.

The costs: integration issues (the shared-code protocol, tier A tests
against both engines) surface after MMP, not before; testers change
`import flopy4` to `import flopy` at the release candidates (a scripted
rename, documented in [`migrating.md`](../migrating.md)). The integration plan rates the
code move as low risk, and the engine risk is exercised by the betas
either way.

**Open: version numbers.** `flopy4` is at `0.0.1.dev0`. Versioning the
pre-releases `4.0.0aN`/`4.0.0bN` lines them up with `flopy==4.0.0` and
avoids a jump from 0.x.

## What MMP means

From [`map.md`](map.md): all core and most peripheral functionality, released to a
wider test audience at USGS and Deltares, beta versioning. Its list
includes rough feature parity with 3.x, user-testing feedback, adapted
3.x docs and examples, comprehensive testing, and finalized maintenance,
release and MF6 version support plans.

The SRS requirements due at MMP, plus the one MVP requirement still open:

| req | MoSCoW | status (2026-11-03) | remaining |
|---|---|---|---|
| FUNC-7 round-trip with identical results (MVP) | C | Not done. [`test.md`](test.md) lists flopy3/4 comparison and round-trip tests as unchecked. | Track A |
| FUNC-8 larger-than-memory | M | Partial. dask is an optional extra; external arrays load eagerly (#516); no xarray IO backend (#368). | Track C |
| FUNC-10 wide range of MF6 versions | S | Mostly. `flopy4 mf6 sync`, [`mf6-versions.md`](../mf6-versions.md); tested against the latest release and MF6 `develop` only. | Decide whether "wide range" needs a test matrix of older releases. |
| FUNC-11 spatial and temporal units | C | Not audited. Grid adapters carry length units. | Audit, or defer past MMP (it's a C). |
| FUNC-14 reproduce the spec | S | Partial. `_contract.py` records the DFN commit; #299 open. | Track B |
| NFR-1 public vs internal API in docs | M | Not done. No API reference in the docs. | Track D |
| NFR-6 documented, type-hinted public API | S | Not done, same reason. | Track D |
| NFR-7 consolidated entry points | S | Partial. #342 (unified output loading) and #232 open. | Track B |

The GitHub MMP milestone has 24 open issues. Many are questions
(#229, #240, #258, #259, #436, #523) that are either decisions for
Track B or can move past MMP. Triage it early, so the milestone matches
this doc.

## MMP gate

- [ ] Tier E (equivalence harness) passes on the registry corpus, with
  any accepted gaps listed. FUNC-7 falls out of this.
- [ ] Round-trip load/write tests over the corpus.
- [ ] The bare-list `stress_period_data` bug fixed.
- [ ] The user-facing API decisions in Track B made and implemented.
  Testers write code against them, so changing them after MMP breaks
  them.
- [ ] Datetime period keys (#518) in, or explicitly deferred.
- [ ] API reference in the docs, public vs internal marked (NFR-1, NFR-6).
- [ ] Concepts doc (#217), and [`migrating.md`](../migrating.md) covering the compat layer.
- [ ] Migration scoreboard running here against MF6's autotests and the
  examples, so the release notes can say how much flopy3 code runs with
  only imports and class names changed, and how much after
  `flopy4 migrate`.
- [ ] Install from GitHub works on Windows, Linux and macOS (SYS-2), with
  the command documented.
- [ ] MMP milestone triaged: each open issue fixed, decided, or moved.

## Tracks

All run at once. The table says what each needs to deliver by MMP; work
after MMP is under "After MMP".

| track | items | by MMP | detail |
|---|---|---|---|
| **A. Engine correctness** | bare-list bug; equivalence harness (tier E) over the registry; round-trip tests; fix what they find | everything | [`replacing-flopy-mf6.md`](plans/integration/replacing-flopy-mf6.md) "Tests", [`test.md`](test.md). **Longest and least predictable. Start first.** |
| **B. API decisions** | `output.head` (integration decision 3); `get_package`/`modelgrid` on Model; `name` vs `sim_name`; accessor naming and `flatten()`/`node`; component naming (#258); parent/child init (#259); unified output loading (#342); the data-shape questions, decided together by one rule: STO types (#229), UZF placeholders (#523), SFR `connectiondata` (#345), packages without a grid (#226) | decided and implemented | [`replacing-flopy-mf6.md`](plans/integration/replacing-flopy-mf6.md) "Open decisions"; [`overview.md`](plans/xarray/overview.md) "Open"; [`layout-logical-decisions.md`](plans/dfn-spec/layout-logical-decisions.md) for #226, #229, #259, #345, #523 |
| **C. Data and xarray** | `to-xarray-constants` fix; datetime period keys (#518, #226); lossless `to_xarray`/`from_xarray` and `dense()` (export phase 1), including an Options section in the representation spec (logical options as data, layout options as encoding, output options off the data) and opt-in views for dynamic derivations (`AUXMULTNAME`, TAS); deferred external arrays (#516) | the fix, #518 and export phase 1; #516 for FUNC-8 | [`export.md`](plans/xarray/export.md), [`datetime-periods.md`](plans/xarray/datetime-periods.md), [`representation.md`](plans/xarray/representation.md), [`layout-logical-decisions.md`](plans/dfn-spec/layout-logical-decisions.md) "Track C" |
| **D. Docs** | API reference; concepts (#217); 3.x examples adapted; [`migrating.md`](../migrating.md) for compat; SDD update once export phase 1 lands | all | [`map.md`](map.md), [`srs.md`](srs.md), [`sdd.md`](sdd.md) |
| **E. Migration** | classify every flopy3 difference (accept, deprecate, break); runtime aliases in flopy4 itself (positional parent, `register_ims_package`, `write_simulation`, `get_package`, `modelgrid`, `*_filerecord`, ...); the shared `Legacy` table; the `flopy4 migrate` codemod; the corpus scoreboard over MF6 autotests and examples. Generated `ModflowXxx` class names stay in flopy 4.x's compat layer | classification, aliases and scoreboard; the codemod if time allows | [`aliases-and-codemod.md`](plans/integration/aliases-and-codemod.md); [`replacing-flopy-mf6.md`](plans/integration/replacing-flopy-mf6.md) "The compat layer" |
| **F. 3.x prep** (flopy `develop`) | 3.x items 1 to 5: utilities out of `flopy/mf6`, the shared-code protocol, upstream patches, deprecations, forward-compatible keywords | nothing required; items 1 and 2 by the `4.x` cut | [`replacing-flopy-mf6.md`](plans/integration/replacing-flopy-mf6.md) "3.x work" |
| **G. Packaging** | devtools release; drop the git dependency; xugrid range; Python 3.14 and the 3.11 question; numpy floor; lazy xugrid import | nothing required (GitHub installs); all by the first release candidate | [`replacing-flopy-mf6.md`](plans/integration/replacing-flopy-mf6.md) Phase 0 item 3; [`overview.md`](plans/xarray/overview.md) (lazy xugrid, grid composition) |

Tracks F and G aren't needed for MMP, but start them now: they're small,
each piece is releasable on its own, and they decide how quickly the
release candidates follow MMP.

### Dependencies between tracks

- Track A's harness finds engine bugs, and fixing them may touch Track C
  (period data, arrays). Keep Track C's changes small until the harness
  is running.
- #226 (packages without a grid), #259 (parent/child init) and #287's
  binding-graph navigation (`Spc.target`, `Model.flow_model`, ...) need
  the same attach operation. Design them together, or the relation ends
  up held in two places.
- Track A's two comparisons check different things: round-trip
  (FUNC-7) preserves layout as given, while the flopy3/flopy4 file
  comparison is logical, normalized by the option labels
  ([`layout-logical-decisions.md`](plans/dfn-spec/layout-logical-decisions.md) "Track A").
- Track E's aliases and codemod rules wait for Track B's naming
  decisions (and default file naming), or they get regenerated.
- Track D's API reference waits for Track B, and the SDD update waits
  for export phase 1 (Track C).

### The longest chain

Equivalence harness → engine fixes → tier E passes → MMP. The other
tracks should finish inside it. If one starts to hold up the gate,
that's the time to add people to it.

## After MMP

From [`replacing-flopy-mf6.md`](plans/integration/replacing-flopy-mf6.md), Phases 2 and 3:

1. Work through MMP feedback. Make integration decision 2 (compat data
   access), informed by the scoreboard numbers and the feedback.
2. Cut `4.x` once the API has settled and the integration plan's "Before
   cutting `4.x`" list is done.
3. Move the old engine to the legacy path, bring `flopy4` in as
   `flopy.mf6`, run tiers A to E there.
4. Release candidates `flopy==4.0.0rcN` from PyPI and conda-forge.
5. GA, then 3.x maintenance for a set time.

## Decisions to make

From the plans this doc links to, ordered by when they're needed:

| decision | needed by | where |
|---|---|---|
| Pre-release version numbers (`4.0.0bN`?) | first alpha | here |
| `output.head`: which side renames (integration 3) | MMP | [`replacing-flopy-mf6.md`](plans/integration/replacing-flopy-mf6.md) |
| Remaining Track B API questions | MMP | Track B |
| The layout/logical rule, and with it #226, #229, #259, #345, #523 | MMP; early, since Track B's other data questions follow from it | [`layout-logical-decisions.md`](plans/dfn-spec/layout-logical-decisions.md) |
| Post #287 before the layout/logical decisions, so Deltares can weigh in on the rule? | before the layout/logical rule | [`layout-logical-decisions.md`](plans/dfn-spec/layout-logical-decisions.md) |
| Default file names (`m.chd` vs `m.chd0.chd`) | the Part 1 aliases; decide early, it changes flopy4's own tests | [`aliases-and-codemod.md`](plans/integration/aliases-and-codemod.md) |
| FUNC-10 test matrix; FUNC-11 in or out of MMP | MMP | SRS |
| Compat data access (integration 2) | `4.x` cut | [`replacing-flopy-mf6.md`](plans/integration/replacing-flopy-mf6.md) |
| Legacy engine and its namespace (integration 1) | `4.x` cut | [`replacing-flopy-mf6.md`](plans/integration/replacing-flopy-mf6.md) |
| Where the top-level modules go (integration 6) | `4.x` cut | [`replacing-flopy-mf6.md`](plans/integration/replacing-flopy-mf6.md), [`overview.md`](plans/xarray/overview.md) |
| numpy floor and Python range (integration 5) | first release candidate | [`replacing-flopy-mf6.md`](plans/integration/replacing-flopy-mf6.md) |
| 3.x keywords in 3.x (integration 4) | 3.x item 5 | [`replacing-flopy-mf6.md`](plans/integration/replacing-flopy-mf6.md) |
| 3.x support window (integration 7) | GA | [`replacing-flopy-mf6.md`](plans/integration/replacing-flopy-mf6.md) |
