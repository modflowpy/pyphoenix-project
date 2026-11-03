# Plans and design notes

Every plan and design note, by topic. Everything under `docs/dev/plans/`
is read in the source tree and isn't part of the built docs; the published
developer docs (SRS, SDD, roadmap, testing) sit one level up. For what's scheduled, and
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

## xarray

[xarray/package.md](xarray/package.md) is the umbrella doc for this area,
with a table of how the others relate.

| Doc | What | Status |
|---|---|---|
| [xarray/package.md](xarray/package.md) | layering an MF6 xarray package inside flopy4 so it can be extracted later | agreed, not scheduled |
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
| [components/reference-fields.md](components/reference-fields.md) | fields that refer to components without owning them (solution models, exchange models) | done |
| [components/user-dir-classes.md](components/user-dir-classes.md) | generating component classes into a per-user directory instead of the installed package | idea |

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
