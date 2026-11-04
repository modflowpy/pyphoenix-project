# Plans and design notes

Plans with work left, research reports and reference notes, by topic.
A plan moves to the [archive](archive/README.md) once nothing in it is
left to do. Everything under `docs/dev/plans/` is read in the source tree
and isn't part of the built docs; the published developer docs (SRS, SDD,
roadmap, testing) sit one level up. For what's scheduled, and
in what order, see [mmp-plan.md](../mmp-plan.md); for milestones, see
[map.md](../map.md).

Status values: **done** (implemented or concluded), **in progress**,
**agreed** (direction decided, work not started), **proposal** (awaiting a
decision), **exploratory** (research, nothing decided), **deferred** or
**idea** (not planned).

## Integration with flopy

| Doc | What | Status |
|---|---|---|
| [integration/replacing-flopy-mf6.md](integration/replacing-flopy-mf6.md) | replacing flopy's mf6 engine with flopy4: 3.x prep, the 4.x layout, the compat layer, test tiers, release order | proposal; release shape decided |
| [integration/aliases-and-codemod.md](integration/aliases-and-codemod.md) | runtime aliases for flopy3 idioms in flopy4, then a `flopy4 migrate` codemod | proposal |
| [integration/modflowapi.md](integration/modflowapi.md) | folding modflowapi into flopy4 as an XMI plugin built from mixins (`plan-api` branch, Feb 2026) | proposal, not started |
| [integration/xmi-api.md](integration/xmi-api.md) | the XMI API that plan would expose, following modflowapi | design, not started |
| [integration/python-models.md](integration/python-models.md) | extending flopy4 to Python-based modeling codes | proposal, not started |

## xarray

[xarray/overview.md](xarray/overview.md) is the umbrella doc for this area,
with a table of how the others relate.

| Doc | What | Status |
|---|---|---|
| [xarray/overview.md](xarray/overview.md) | layering an MF6 xarray package inside flopy4 so it can be extracted later | agreed, not scheduled |
| [xarray/representation.md](xarray/representation.md) | the spec: grid dims and coordinates, the tree, period data, how it relates to netCDF, CF, UGRID and MF6 NetCDF | draft |
| [xarray/export.md](xarray/export.md) | lossless `to_xarray`/`from_xarray`, `dense()`, `flatten()`, cell layouts | agreed, not started |
| [xarray/datetime-periods.md](xarray/datetime-periods.md) | datetime period keys (#518), then `create_tdis` (#226) | in progress |
| [xarray/rotated-grid-index.md](xarray/rotated-grid-index.md) | DIS coordinates, rotation, `CellIndex`, z selection, the `.grid` accessor | mostly done; "Next" list live |
| [xarray/rch-evt-layer.md](xarray/rch-evt-layer.md) | z coordinates for RCHA/EVTA arrays | not started |
| [xarray/tas-interpolation.md](xarray/tas-interpolation.md) | evaluating time-array series in the period view | ready, not started |
| [xarray/combined-index.md](xarray/combined-index.md) | a combined grid index on `CellIndex` | deferred |

## Components and code generation

| Doc | What | Status |
|---|---|---|
| [components/mixin-fields.md](components/mixin-fields.md) | what mixins rely on in the DFNs, and how the tests guard it | reference; to become a dev doc |
| [components/user-dir-classes.md](components/user-dir-classes.md) | generating component classes into a per-user directory instead of the installed package | idea |

## Lists

| Doc | What | Status |
|---|---|---|
| [lists/list-fields.md](lists/list-fields.md) | list fields: `list_()`, item classes, `ItemTable` storage | reference; to become a dev doc |
| [lists/record-unify.md](lists/record-unify.md) | list shape key, line records on field functions, the `Item`/`Record` merge | steps 1-3 done (#463); the merge is open |
| [lists/binary-list-shapes.md](lists/binary-list-shapes.md) | which blocks MF6 can read binary list input into | reference |

## Reading and writing

| Doc | What | Status |
|---|---|---|
| [io/converter-simplification.md](io/converter-simplification.md) | one DFN-driven structure/unstructure path, two loaders side by side | done on the unmerged `simplify-converter` branch |
| [io/loader-comparison.md](io/loader-comparison.md) | the basic and typed loaders measured against each other | report (2026-10-21) |

## Maintenance

| Doc | What | Status |
|---|---|---|
| [maintenance/backlog.md](maintenance/backlog.md) | small open items that don't belong to a live plan | open |
| [maintenance/dead-code-audit.md](maintenance/dead-code-audit.md) | unused code in hand-written `flopy4/` | sections 1-4 done; 5 open |
| [maintenance/simplification-survey.md](maintenance/simplification-survey.md) | where hand-written `flopy4/mf6` could be simpler | survey; nothing started |
| [maintenance/dev-docs.md](maintenance/dev-docs.md) | turning the reference notes here into published developer docs | not started |

## The DFN spec

Research on whether the DFN spec should describe MF6 input at two levels,
logical and layout, and what that means for flopy4 (discussion #287).
Start with [dfn-spec/overview.md](dfn-spec/overview.md), which defines the terms
the others use.

| Doc | What | Status |
|---|---|---|
| [dfn-spec/overview.md](dfn-spec/overview.md) | concepts, hypotheses, plan | exploratory |
| [dfn-spec/option-classification.md](dfn-spec/option-classification.md) | every DFN option labelled layout, logical or output | done |
| [dfn-spec/constraint-audit.md](dfn-spec/constraint-audit.md) | kinds of input constraint, where each is enforced, and what could express it | done |
| [dfn-spec/dfn-gaps.md](dfn-spec/dfn-gaps.md) | rules MF6 enforces that the DFNs don't state, and memory catalog gaps; for MF6 and devtools developers | report |
| [dfn-spec/layout-logical-decisions.md](dfn-spec/layout-logical-decisions.md) | the layout/logical rule applied to MMP issues #226, #229, #259, #345, #523 | proposal |
| [dfn-spec/schema-polymorphism.md](dfn-spec/schema-polymorphism.md) | schema polymorphism (#287) vs. component key roles (devtools #405) | notes |
| [dfn-spec/polymorphism-hypotheses.md](dfn-spec/polymorphism-hypotheses.md) | three hypotheses the #287 findings point to | working notes |

## Archive

Finished, superseded and abandoned plans are in [archive/](archive/README.md),
as they were last written. That includes the plans for reference fields,
solution and exchange binding, binding rows, package naming, period lists,
load performance and the writer's dead code.
