# Converter simplification plan (structure / unstructure)

Status: **done**, apart from D5 and D6 (skipped for now) and the
follow-ups under "Later". Written 2026-09-22 against `fe5423c` and revised
2026-10-19/20 after rebasing onto `develop` (`916c2f8b`). From 2026-10-20
the plan was two loaders built side by side, then compared. Trimmed
2026-10-22 to the results; the full plan, with each phase as planned, is
in this file's git history (before this trim, `65af7491`). Rebased
2026-10-23 onto `develop` at `d14e5fb2` (#503, flopy3's period-data
keywords), with devtools at `07d1273a`. Squashed and rebased 2026-11-05
onto `develop` at `be07090a` (#539), which also took the typed loader off
this branch: see "The typed loader" below. The commit hashes here are on
`typed-loader-parked` (`f46cfeca`), the pre-squash history.

The work is a refactor on the current attrs object model, independent of
the `pydantic-plan` migration. The round-trip suite
(`test/mf6/test_mf6_io_roundtrip.py`), the load snapshots and the
written-file snapshots are the safety net. The one API change is STO's
period value (decision 1).

## Goal

Replace the multi-pass, exception-driven ingress (`structure.py`) and the
type-sniffing egress (`unstructure.py`) with one schema-driven model of an
MF6 block, used the same way in both directions.

Before, on `develop` @ `916c2f8b`:
- **Ingress** ran seven passes. Each classified fields from their Python
  annotations, guessed a list's taggedness from its block's size, and
  grouped repeating blocks its own way. There were three array readers,
  and six copies of the kwarg-name rule that disagreed.
- **Egress** dispatched on runtime value types through about a dozen
  `isinstance` branches. It hardcoded `maxbound` and `solutiongroup 1`,
  and had separate paths for packages and other components.

## Where it ended up

- **One loader here** (`converter/ingress/structure.py`, `_Load`): the
  basic grammar's token rows, with block structure from the DFNs stored
  with the classes.
  - **Base class** (`ComponentLoad`): assembling a repeating block's values
    by header, fill-forward and clearing, list rows into `Item`s, child
    bindings, and the instance's `WriteContext`. It has one subclass on
    this branch, and stays split for the typed loader's.
- **One egress path** (`egress/unstructure.py`, `_Unstructure`), the
  inverse of `_Load`. It walks the DFN's blocks in order and writes each
  field by its DFN type.
- **Stored DFNs.** Sync writes the DFNs it generated the classes from to
  `flopy4/mf6/dfns`, as TOML. `spec.dfn(cls)` loads one when first asked
  for; `spec.block_keys(cls, block)` gives a block's row keys, dynamic
  keys and untagged field. `spec.attr_names(cls)`, from codegen, maps
  each DFN field to its class attribute.
- **What the classes carry**, written by codegen: `dfn_name`; `headers`,
  each repeating block's `Header(kind, index)` (D7); and each field's
  `block`, `fill_forward` and type metadata.

## Phases

Each kept the round-trip suite and the load and written-file snapshots
green when it landed.

### Shared

- **S1. Name mapping** (`971db3f6`). Codegen records the attribute it
  names for each DFN field (`make.attr_names`), so there's one naming
  rule. The loader switch from this commit left with the typed loader.
- **S2. Egress mirror** (`0995bc85`). One path for every component.
  - `maxbound` is read from the class's property, and the `solutiongroup
    1` hack is gone: a field holding one value is the first occurrence's.
  - The rows naming children come from `bindings`, the inverse of
    `_resolve_bindings`.
  - Written files changed only in field order, now the DFN's: `MXITER`
    before the solution rows, and EVT's `MAXBOUND` before `NSEG`.

### Track A: the basic loader

- **A1. Stored DFNs** (`ac0e06ee`, lazy loading `58fd00e0`). Sync stores
  the DFNs again (`_store_dfns`, dropped in #455). `spec.dfn`,
  `block_keys` and `following_tags` wrap the devtools helpers in one
  place.
  - A first attempt emitted a `BlockSpec` per class and was dropped: it
    restated the DFN in a vocabulary of its own.
- **A2. Value parsers** (`aa840941`). `_read_array` reads every grid
  array (griddata, G/A period, TAS time), its length from the field's DFN
  shape. `_tagged_value` and `parse_list` serve every block.
  - `FACTOR` is applied on load and not kept (`write-options-plan.md`, in
    the archive).
- **A3. Ingress loop** (`ed1185e2`). `structure_component` reads the
  DFN's blocks in order, options and dimensions first.
  - `_occurrences` groups blocks by name and header.
  - A row goes to the field of its own block whose key it begins with;
    the rest go to the untagged field, or to `_resolve_bindings`.
  - Passes 1–4, the block-size inference and `repeating_array_key_type`
    are gone.

### The typed loader (not on this branch)

Phases B (typed load, B1-B4) and C (comparing the loaders) were built here
and moved off in the 2026-11-05 rebase. They're on `typed-loader-parked`,
to be rebuilt on a `typed-loader` branch stacked on this one, with the
develop changes this rebase ported into `_Load` ported there too. That
branch doesn't exist yet. `typed.lark`, the generated grammars, `loads_typed`
and `_check_typed_grammar` here are `develop`'s, unchanged. C's results,
from before the rebase, are in
[`loader-comparison.md`](loader-comparison.md).

### D: cleanups from the post-C audit

The audit (2026-10-21, at `0fb2ef70`) counted +405 code lines on the
branch. The basic loader and egress were about +30 together; the typed
loader about +360.

- **D1. One child-binding predicate** (`f68645ef`): `spec.binding_fields`,
  used in all five places that had their own.
- **D2. One header parse**  (`835f7d4c`).
- **D3. `_resolve_bindings` rewritten** (`7aa6139c`). `_binding_target`
  makes one ftype comparison over each field's classes, and one context
  is carried through a block, gaining dims as providers load.
- **D4. `_Load.body` untangled** (`b3cbd503`). `_groups` puts each row
  with the records after it, so the loop is a plain `for`. OC's `HEAD`
  direction check moved to `field_of`, for file records only (``XT3D
  [RHS]`` has an optional second keyword).
- **D5. Value kind from the DFN on ingress.** *Skipped for now.* While
  both loaders stay, none of the annotation helpers (`item_list_type`,
  `block_list_type`, `_per_header`, ...) could go: the typed loader, the
  shared code and egress use them. So this would only add a second
  dispatch. Revisit with deleting a loader.
- **D6. Two sources of truth at runtime** (the classes and the stored
  DFNs, joined by `attr_names`). *Skipped for now,* with D5. Storing the
  names at sync time stays in "Later".
- **D7. Header kinds from the generated classes** (`bf264dda`,
  `00051dee`).
  - Codegen writes `headers: ClassVar[dict[str, Header]]` from the DFN's
    `block.header`:
    - the 59 period blocks: `Header("integer", index=True)`;
    - Simulation's solution groups: `Header("integer")`;
    - TAS: `Header("double")`;
    - OBS: `Header("record")`.
  - `index` is the DFN's: devtools marks IPER `index = true` (dd9bd848).
  - `_header`, egress's `occurrences` and `annotate_arrays`
    read `headers`, so no code names the `period` or `time` block.

## Representation decisions

1. **STO period: done** (`d3e9feb4`). devtools now names the merged
   field `stress_period_data`.
   - Codegen emits it as one word per period:
     `stress_period_data: Optional[dict[int, Literal["steady-state",
     "transient"]]]`, filled forward.
   - `string(valid=...)` keeps a value as the DFN spells it, whatever its
     case.
   - Egress writes it uppercase, as keywords are.
   - `stress_period_data={0: [("STEADY-STATE",)]}` is now
     `stress_period_data={0: "steady-state"}`.
   - flopy3's `steady_state=` / `transient=` (#503) convert to this form
     (`flopy4.mf6.legacy.sto_period_data`).
2. **`stress_period_data` naming: done upstream.** devtools #399 names
   every fill-forward period list `stress_period_data` in the DFNs, as
   codegen already named the attribute, so the generated classes didn't
   change. What's left in codegen isn't about the DFN's name: the list is
   the private `_stress_period_data`, aliased `stress_period_data`, for
   `Package`'s DataFrame setter. flopy3's old names (`perioddata`, ...)
   are #503's `_LEGACY_PERIOD_KWARGS`.

G/A period arrays are sparse per-period dicts on `develop`
(`flopy4.mf6.period_arrays`), the same `{header: value}` shape as every
repeating block.

## The block model

These are the rules both directions follow, and the schema facts they
rest on. They were re-scanned 2026-10-19 over the modflow6 DFNs at
`2.0.0.dev3`: 368 blocks.

> A block is an ordered set of fields. A body row whose first token is a
> tagged field's key belongs to that field. Every other row belongs to the
> block's untagged field, and there is at most one of those, last.

- **Where a tagged key comes from:**
  - the field's name;
  - a record's or file record's keyword (`ts6`, `obs6`, `gwfhead`);
  - a tagged list's item keyword (OC's `SAVE` / `PRINT`);
  - a dynamic key, from the values of the field its `fk` names (G/A
    `aux`, keyed by `auxiliary` names).
- **Where untagged fields occur:** 124 blocks have one and 244 none.
  Simulation's `solutiongroup` is the only block where it isn't alone
  (tagged `mxiter`, then the list).
- **Repetition within a block:** a field occurs once, or is a `List`,
  tagged or untagged.
- **Repetition of a block:** a block with a header repeats. Its value is
  `{header: body}`, the header read by its kind in the class's `headers`.
  `fill_forward` is about meaning, not parsing: an absent period keeps
  the previous one's values.

| block | fill_forward | fields | components |
|---|---|---|---|
| period | yes | one untagged list | list-based stress packages |
| period | yes | tagged list | OC (`output`) |
| period | yes | tagged arrays + tagged `aux` list | G/A packages, `utl-spca` |
| period | yes | one untagged string | `*-sto` |
| time | no | one untagged array | `utl-tas` |
| solutiongroup | no | tagged integer + untagged list | `sim-nam` |
| continuous | no | one untagged list, record header | `utl-obs` |

## Benchmarks

- **Baseline:** recorded in [discussion
  #55](https://github.com/modflowpy/pyphoenix-project/discussions/55#discussioncomment-18978194),
  with the harness in `benchmarks/`.
- **Rerun after S2** (2026-10-21, against the merge base `c5c606eb`, basic
  loader):
  - load and write: no regression beyond noise;
  - peak memory: within ±5% everywhere;
  - cold start: the first load took 0.26 s against 0.21 s. That's the
    stored DFNs the model needs plus building codegen's spec for
    `attr_names` (see "Later").
- **Phase C:** the typed loader's numbers are in `loader-comparison.md`.

## devtools follow-ups

- **Extend `Block._check_field_order` to untagged fields of any type**
  (at most one per block, and last), so the converter can rely on it.
- **Make `_leading_tags` / `_is_dynamic_key` public** (a `Field.tags`
  property, say). flopy4 wraps them in `spec.py` until then.

## Later

Each is its own change.

- **Deleting a loader**, if decided (see `loader-comparison.md`). Deleting the basic loader
  takes the stored DFNs with it, once egress reads the classes' fields.
  The size at stake:
  - typed: ~360 code lines, ~1,300 with grammar generation and templates,
    plus 6,581 lines of generated grammars;
  - basic: ~450 code lines.
- **Attribute names at sync time.** `spec.attr_names` builds codegen's
  spec of each class on its first load, most of the cold-start gap
  above. Sync could store the names, as it stores the DFNs.
- **An auxiliary variable named like a field:** the typed grammar parses
  an aux named RECHARGE as the field. No corpus file does it.
- **A TAS time's array isn't recorded in `ArrayIO`** by either loader, so
  its read options aren't kept on write.
- **`test060_gms_ets`** loads under neither loader.
- **Load errors don't name the file.** The typed loader's give a line and
  column; the basic loader's give neither.
- **The basic loader is lenient where MF6 isn't.** A missing `END` reads
  the next `BEGIN` as an unknown option, and a wrong-typed computed field
  (`MAXBOUND two`) is ignored.
- **The typed loader's memory:** 1.8× basic's peak on
  `test016_Keating_dev` and 1.7× on `test045_lake4ss_dev`. Worth looking
  into before deleting the basic loader.
- **The writer's `field_type`** (`simplification-survey.md` #5): egress
  knows each field's DFN type, so could pass it along.

Out of scope: the index-domain / time-dimension sentinel discussion.

## History

The first draft's Phase 0 survey (load → write → reload over 239 corpus
models) found ten pre-existing issues. All were fixed on `develop` before
the refactor:
- ISO datetimes, float precision, model subdirectories, trailing tokens
  and a single-name `AUXILIARY`;
- aux-named G/A period arrays (devtools #371);
- a repeated `TS6` (devtools #368);
- TAS-sourced period arrays (#413);
- ungenerated packages;
- quoted strings (#462).

The Phase 0 harness is `test/mf6/test_mf6_io_roundtrip.py`.
