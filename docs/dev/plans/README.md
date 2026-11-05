# Plans and design notes

Plans with work left, research reports and reference notes, by topic. They
reflect current understanding and change as it does. A plan moves to the
[archive](archive/README.md) once nothing in it is left to do.
Everything under `docs/dev/plans/` is read in the source tree and isn't
part of the built docs; the published developer docs (SRS, SDD, roadmap,
testing) sit one level up. For what's scheduled, and in what order, see
[mmp-plan.md](../mmp-plan.md); for milestones, see [map.md](../map.md).

## Integration with flopy

| Doc | What |
|---|---|
| [integration/replacing-flopy-mf6.md](integration/replacing-flopy-mf6.md) | replacing flopy's mf6 engine with flopy4: 3.x prep, the 4.x layout, the compat layer, test tiers, release order |
| [integration/aliases-and-codemod.md](integration/aliases-and-codemod.md) | runtime aliases for flopy3 idioms in flopy4, then a `flopy4 migrate` codemod |
| [integration/period-list-values.md](integration/period-list-values.md) | not started: flopy3's `get_data`, `set_data`, `.array` and `.data` on `PeriodRows`, if unchanged 3.x scripts become a goal |
| [integration/modflowapi.md](integration/modflowapi.md) | speculative, not for 4.x: folding modflowapi into flopy4 as an XMI plugin, with modflowapi's API |

## xarray

[xarray/overview.md](xarray/overview.md) is the umbrella doc for this area.

| Doc | What |
|---|---|
| [xarray/overview.md](xarray/overview.md) | layering an MF6 xarray package inside flopy4 so it can be extracted later |
| [xarray/representation.md](xarray/representation.md) | the spec: grid dims and coordinates, the tree, period data, how it relates to netCDF, CF, UGRID and MF6 NetCDF |
| [xarray/export.md](xarray/export.md) | lossless `to_xarray`/`from_xarray`, `dense()`, `flatten()`, cell layouts |
| [xarray/out-of-core.md](xarray/out-of-core.md) | larger-than-memory models (FUNC-8): streaming writes, lazy load, lazy lists, a faster text writer, the tests that prove them |
| [xarray/datetime-periods.md](xarray/datetime-periods.md) | datetime period keys (#518), then `create_tdis` (#226) |
| [xarray/rotated-grid-index.md](xarray/rotated-grid-index.md) | DIS coordinates, rotation, `CellIndex`, z selection, the accessor, and what's next |
| [xarray/rch-evt-layer.md](xarray/rch-evt-layer.md) | z coordinates for RCHA/EVTA arrays |
| [xarray/tas-interpolation.md](xarray/tas-interpolation.md) | evaluating time-array series per time step |
| [xarray/combined-index.md](xarray/combined-index.md) | a combined grid index on `CellIndex`, and why not yet |

## Components and code generation

| Doc | What |
|---|---|
| [components/mixin-fields.md](components/mixin-fields.md) | what mixins rely on in the generated classes, and how sync checks it |
| [components/user-dir-classes.md](components/user-dir-classes.md) | generating component classes into a per-user directory instead of the installed package |
| [components/constructor-stubs.md](components/constructor-stubs.md) | generated `.pyi` stubs so type checkers accept what constructors accept, then `py.typed` |
| [../pydantic-object-model-plan.md](../pydantic-object-model-plan.md) | attrs vs. pydantic for the object model; a complete migration on draft #367, undecided |

## Lists

| Doc | What |
|---|---|
| [lists/list-fields.md](lists/list-fields.md) | list fields: representation, `ItemTable` storage, row layout |
| [lists/record-unify.md](lists/record-unify.md) | merging `Item` into `Record` |
| [lists/binary-list-shapes.md](lists/binary-list-shapes.md) | which blocks MF6 can read binary list input into |

## Reading and writing

| Doc | What |
|---|---|
| [io/converter-simplification.md](io/converter-simplification.md) | one DFN-driven structure/unstructure path, typed loader moved off to `typed-loader` (unmerged `simplify-converter` branch) |
| [io/converter-rebase.md](io/converter-rebase.md) | rebasing `simplify-converter` onto develop, with the typed loader kept current on a stacked `typed-loader` branch |
| [io/loader-comparison.md](io/loader-comparison.md) | the basic and typed loaders measured against each other |

## Maintenance

| Doc | What |
|---|---|
| [maintenance/backlog.md](maintenance/backlog.md) | small open items that don't belong to a plan |
| [maintenance/simplification-survey.md](maintenance/simplification-survey.md) | where hand-written `flopy4/mf6` could be simpler |
| [maintenance/dev-docs.md](maintenance/dev-docs.md) | turning the reference notes here into published developer docs |

## The DFN spec

Research on whether the DFN spec should describe MF6 input at two levels,
logical and layout, and what that means for flopy4 (discussion #287).
Start with [dfn-spec/overview.md](dfn-spec/overview.md), which defines the
terms the others use.

| Doc | What |
|---|---|
| [dfn-spec/overview.md](dfn-spec/overview.md) | concepts, hypotheses, evidence, next steps |
| [dfn-spec/option-classification.md](dfn-spec/option-classification.md) | every DFN option labelled layout, logical or output |
| [dfn-spec/constraint-audit.md](dfn-spec/constraint-audit.md) | kinds of input constraint, where each is enforced, and what could express it |
| [dfn-spec/dfn-gaps.md](dfn-spec/dfn-gaps.md) | rules MF6 enforces that the DFNs don't state, and memory catalog gaps; for MF6 and devtools developers |
| [dfn-spec/layout-logical-decisions.md](dfn-spec/layout-logical-decisions.md) | the layout/logical rule applied to MMP issues #226, #229, #259, #345, #523 |
| [dfn-spec/schema-polymorphism.md](dfn-spec/schema-polymorphism.md) | schema polymorphism (#287) vs. component key roles (devtools #405) |
| [dfn-spec/ddl-export.md](dfn-spec/ddl-export.md) | working plan, not started: run the DDL slice's rules on real models loaded with flopy4 |

## Archive

Finished, superseded and abandoned plans are in [archive/](archive/README.md),
as they were last written.
