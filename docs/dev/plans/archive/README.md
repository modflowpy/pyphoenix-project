# Archived plans

Finished, superseded or abandoned plans, kept for their rationale. They're
committed as they were last written: statuses, branch names, line numbers
and paths are as of then, and many name files at the repo root, where the
notes used to live. Live plans are in the [index](../README.md).

## Object model, codegen and fields

| Doc | What | Outcome |
|---|---|---|
| [2024-idm.md](2024-idm.md), [2024-ofm.md](2024-ofm.md), [2024-notes.md](2024-notes.md), [2024-first-meeting.md](2024-first-meeting.md) | the 2024 input data model, object-file mapping, goals and first-meeting outline (`backup` branch) | historical |
| [mf6-object-model-plan.md](mf6-object-model-plan.md) | the MF6 object model | done |
| [backend-refactor-plan.md](backend-refactor-plan.md) | attrs components with on-demand xarray views instead of xattree proxying | done, as the xattree removal |
| [xattree-removal-plan.md](xattree-removal-plan.md), [xattree-child-naming-plan.md](xattree-child-naming-plan.md) | dropping xattree | done (#356); child naming superseded |
| [protocols-plan.md](protocols-plan.md) | dimension resolution protocols and mixin | done |
| [on-representations.md](on-representations.md) | DFN-vs-class representation mismatches the parser handled (`load` branch) | historical |
| [codegen-comparison.md](codegen-comparison.md), [codegen-recommendation.md](codegen-recommendation.md), [pydantic-prototype-summary.md](pydantic-prototype-summary.md), [model-rebuild-explained.md](model-rebuild-explained.md) | attrs vs. pydantic for generated classes (`plan-codegen` branch) | superseded by the plan below |
| [pydantic-object-model-plan.md](pydantic-object-model-plan.md) | attrs vs. pydantic, revised (draft #367) | stale |
| [field-functions-plan.md](field-functions-plan.md) | one field function per DFN field type | done (#463) |
| [record-values-plan.md](record-values-plan.md) | plain values for every record field | done |
| [mypy-converter-plan.md](mypy-converter-plan.md) | letting mypy see field converters | never merged (draft #433); in the [backlog](../maintenance/backlog.md) |
| [nested-keystring-union-plan.md](nested-keystring-union-plan.md) | typing OC's nested `ocsetting` unions | done |
| [array-equality-spec.md](array-equality-spec.md) | array-aware component equality | done (#394) |
| [codegen-base-class-removal-plan.md](codegen-base-class-removal-plan.md) | generating TDIS and NCF instead of hand-written bases | done (#385) |
| [dis-base-class-removal-plan.md](dis-base-class-removal-plan.md) | generating the discretization packages | done (#391) |
| [disv-plan.md](disv-plan.md) | what #391 delivered for DISV, and what was left | historical |
| [codegen-role-removal-plan.md](codegen-role-removal-plan.md) | removing the codegen "role" layer | proposal, not taken up |
| [model-codegen-plan.md](model-codegen-plan.md) | generating the model classes | done (#411) |
| [child-fields-plan.md](child-fields-plan.md), [links-from-dfns-plan.md](links-from-dfns-plan.md) | child fields and links from DFN component links | done (#395, #396) |
| [package-binding-plan.md](package-binding-plan.md) | packages that hold the components their file records name (e.g. `TS6 FILEIN`) | see doc |
| [reference-fields-plan.md](reference-fields-plan.md) | generic resolve and check for reference fields | done (#499) |
| [reference-fields-notes.md](reference-fields-notes.md) | fields that refer to components without owning them (solution models, exchange models) | done |
| [solution-binding.md](solution-binding.md) | how solutions and exchanges are tied to their models (#285) | done (#496, #497) |
| [binding-rows.md](binding-rows.md) | generating name-file binding rows from the DFNs | done (#526) |
| [package-naming.md](package-naming.md) | default package names and filenames, and the one-file-per-component check | done (#495) |
| [cellid-node-arrays.md](cellid-node-arrays.md) | devtools' cellid arrays and what changes in flopy4 | see doc |
| [dev3-migration-gaps.md](dev3-migration-gaps.md) | gaps hit migrating to DFN schema dev3 | resolved |
| [develop-shared-fixes.md](develop-shared-fixes.md) | fixes to carry from `pydantic-plan` to develop | obsolete |

## Dimensions, lists and periods

| Doc | What | Outcome |
|---|---|---|
| [dimension-issues.md](dimension-issues.md) | dimension follow-ups from #167, as issue drafts | done except one item |
| [list-dim-default-problem.md](list-dim-default-problem.md) | linked dimensions: explicit value vs. default | deferred |
| [boundname-plan.md](boundname-plan.md) | boundnames and token text end to end | done (#470, #478) |
| [period-lists.md](period-lists.md) | an xarray form for list packages' period data | done (#476) |
| [period-storage-plan.md](period-storage-plan.md) | per-period storage for period arrays | implemented on a branch; see doc |
| [repeating-block-header-generalization.md](repeating-block-header-generalization.md) | repeating blocks via `Block.header` | partly adopted |
| [flopy3-period-names-plan.md](flopy3-period-names-plan.md) | flopy3's period-data argument names | done (#503) |
| [tas-shorthand-typing-plan.md](tas-shorthand-typing-plan.md) | typing the TAS name shorthand | proposal |

## Loading, writing and performance

| Doc | What | Outcome |
|---|---|---|
| [plan.md](plan.md) | the Track A / Track B development plan (input loading) | done |
| [loader-roadmap.md](loader-roadmap.md) | the input loader roadmap | superseded |
| [class-driven-reader-plan.md](class-driven-reader-plan.md) | dropping the reader's runtime DFN dependency | done (#455) |
| [load-context-plan.md](load-context-plan.md) | load context | done (#418) |
| [model-relpath-plan.md](model-relpath-plan.md) | model directories | implemented on a branch; see #421 |
| [load-corpus-gaps.md](load-corpus-gaps.md) | `Simulation.load()` gaps on the test corpus | done |
| [load-branch-todo.md](load-branch-todo.md) | TODO list from the `load` branch | historical |
| [typed-grammar-issues.md](typed-grammar-issues.md) | generated typed grammars falling back to the basic parser (`load` branch) | historical |
| [typed-grammar-remarks.md](typed-grammar-remarks.md), [typed-grammar-trailing-remarks.md](typed-grammar-trailing-remarks.md) | whether the typed grammar keeps trailing remarks, and its speed | answered: keep remarks |
| [typed-loader-wiring.md](typed-loader-wiring.md) | making the typed loader a selectable alternative | superseded by [converter-simplification.md](../io/converter-simplification.md) (unmerged `simplify-converter`) |
| [typed-loader-perf.md](typed-loader-perf.md) | load performance work | done (#474-#484); paused |
| [optimization-plan.md](optimization-plan.md) | input-load optimizations, basic loader first | superseded by [typed-loader-perf.md](typed-loader-perf.md) |
| [load-baseline-plan.md](load-baseline-plan.md) | baseline load benchmarks, flopy3 vs. flopy4 | folded into #482 |
| [benchmark-infra-plan.md](benchmark-infra-plan.md) | benchmark infrastructure | done (#482) |
| [io-benchmark-results.md](io-benchmark-results.md) | flopy4 vs. flopy3 IO benchmark, 2026-10-16 | stale |
| [write-options-plan.md](write-options-plan.md) | write options | implemented locally; see #454 |
| [dead-code-audit.md](dead-code-audit.md) | unused code in hand-written `flopy4/` | done (#509, #510, #528, #530, #531); one item in the [backlog](../maintenance/backlog.md) |
| [writer-dead-code.md](writer-dead-code.md) | the writer's dead xarray-Dataset list path | done (#505) |

## xarray and ecosystem

| Doc | What | Outcome |
|---|---|---|
| [spatial-index-design.md](spatial-index-design.md) | the first spatial index design (`xarray-index`, #278) | superseded by [rotated-grid-index.md](../xarray/rotated-grid-index.md) |
| [netcdf-spec-plan.md](netcdf-spec-plan.md) | what of a NetCDF spec belongs in devtools vs. flopy4 | superseded by [representation.md](../xarray/representation.md) |
| [ecosystem-sync-plan.md](ecosystem-sync-plan.md) | syncing DFNs and tooling across the MF6 ecosystem | done |

## DFN spec research

| Doc | What | Outcome |
|---|---|---|
| [polymorphism-hypotheses.md](polymorphism-hypotheses.md) | working notes on three hypotheses from the #287 findings | superseded by [dfn-spec/overview.md](../dfn-spec/overview.md) |

## Follow-up lists

| Doc | What | Outcome |
|---|---|---|
| [followups-after-row-layout.md](followups-after-row-layout.md) | follow-ups after row layout, boundnames and conditional fields | items 1-3 done; 4 and 5 moved to the [backlog](../maintenance/backlog.md) |
| [open-followups.md](open-followups.md) | leftovers from the plans archived by 2026-10-19 | the one open item moved to the [backlog](../maintenance/backlog.md) |
