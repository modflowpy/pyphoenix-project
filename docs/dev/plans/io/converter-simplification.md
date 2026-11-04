# Converter simplification (structure / unstructure)

One schema-driven model of an MF6 block, used the same way to read and to
write, with two loaders built side by side. Done on the unmerged
`simplify-converter` branch (42 commits ahead of develop, last rebased onto
`d14e5fb2`, #503). It's a refactor on the attrs object model. The safety
net is the round-trip suite (`test/mf6/test_mf6_io_roundtrip.py`) and the
load and written-file snapshots, green under both loaders. The one API
change is STO's period value.

## Before

On develop at `916c2f8b`:

- **Ingress** (`structure.py`) ran seven passes. Each classified fields
  from their Python annotations, guessed a list's taggedness from its
  block's size, and grouped repeating blocks its own way. There were three
  array readers, and six copies of the kwarg-name rule that disagreed.
- **Egress** (`unstructure.py`) dispatched on runtime value types through
  about a dozen `isinstance` branches, hardcoded `maxbound` and
  `solutiongroup 1`, and had separate paths for packages and other
  components.

## On the branch

- **Two loaders.** `load(..., loader="basic" | "typed")`, from
  `LoadContext.loader` (inherited by children); basic is the default. The
  tests take `--loader`.
  - **Basic** (`converter/ingress/structure.py`, `_Load`): the basic
    grammar's token rows, with block structure from the DFNs stored with
    the classes. `structure_component` reads the DFN's blocks in order,
    options and dimensions first. `_occurrences` groups blocks by name and
    header; `_groups` puts each row with the records after it. One array
    reader (`_read_array`) for griddata, G/A period and TAS time arrays,
    its length from the DFN shape. `FACTOR` is applied on load and not
    kept.
  - **Typed** (`converter/ingress/typed.py`, `_TypedLoad`): one generated
    grammar per component, its rules named after class attributes. It reads
    no DFN at runtime. The grammars skip what MF6 skips: unknown blocks and
    lines, `DEV_` options, the rest of a line past a field's values, an
    array's name-row remark. Built parsers are cached on disk
    (`FLOPY4_CACHE_DIR` overrides the location), keyed by grammar text and
    lark and Python versions; all 129 load in 0.74 s warm against 4.4 s to
    build.
  - **Shared base** (`ComponentLoad`): a repeating block's values by
    header, fill-forward and clearing, list rows into `Item`s, child
    bindings, and the instance's `WriteContext`. Only the per-value step
    differs.
- **One egress path** (`egress/unstructure.py`, `_Unstructure`), the
  inverse of `_Load`. It walks the DFN's blocks in order and writes each
  field by its DFN type, for every component. `maxbound` comes from the
  class's property; a field holding one value is the first occurrence's
  (no `solutiongroup 1` hack); the rows naming children come from
  `bindings`. Written files changed only in field order, now the DFN's.
- **Stored DFNs.** Sync writes the DFNs it generated from to
  `flopy4/mf6/dfns` as TOML (`_store_dfns`, dropped in #455, restored).
  `spec.dfn(cls)` loads one lazily; `spec.block_keys(cls, block)` gives a
  block's row keys, dynamic keys and untagged field; `spec.attr_names(cls)`,
  from codegen, maps DFN fields to class attributes, so there's one naming
  rule. A first attempt emitted a `BlockSpec` per class; it restated the
  DFN in its own vocabulary and was dropped.
- **What the classes carry**, from codegen: `dfn_name`; `headers`, each
  repeating block's `Header(kind, index)` (period blocks
  `Header("integer", index=True)`, solution groups `Header("integer")`,
  TAS `Header("double")`, OBS `Header("record")`); and each field's
  `block`, `fill_forward` and type metadata. No code names the `period` or
  `time` block.
- **One child-binding predicate**, `spec.binding_fields`; one header parse
  for both loaders; `_resolve_bindings` with one ftype comparison per
  field and one context carried through a block.
- **STO period** is one word per period,
  `stress_period_data: Optional[dict[int, Literal["steady-state",
  "transient"]]]`, filled forward and written uppercase:
  `{0: [("STEADY-STATE",)]}` becomes `{0: "steady-state"}`. flopy3's
  `steady_state=`/`transient=` convert to it
  (`flopy4.mf6.legacy.sto_period_data`).

Not done: taking the value kind from the DFN on ingress, and having one
runtime source of truth instead of the classes plus the stored DFNs joined
by `attr_names`. While both loaders stay, the annotation helpers
(`item_list_type`, `block_list_type`, `_per_header`, ...) can't go, so
these would only add a second dispatch. Revisit with deleting a loader.

## The block model

The rules both directions follow, from a scan of the modflow6 DFNs at
`2.0.0.dev3` (368 blocks):

> A block is an ordered set of fields. A body row whose first token is a
> tagged field's key belongs to that field. Every other row belongs to the
> block's untagged field, and there is at most one of those, last.

- **A tagged key** is the field's name; a record's or file record's
  keyword (`ts6`, `obs6`, `gwfhead`); a tagged list's item keyword (OC's
  `SAVE`/`PRINT`); or a dynamic key from the values of the field its `fk`
  names (G/A `aux`, keyed by `auxiliary` names).
- **Untagged fields:** 124 blocks have one, 244 none. Simulation's
  `solutiongroup` is the only block where it isn't alone (tagged `mxiter`,
  then the list).
- **Within a block** a field occurs once, or is a list, tagged or
  untagged.
- **A block with a header repeats.** Its value is `{header: body}`, the
  header read by its kind in `headers`. `fill_forward` is about meaning,
  not parsing: an absent period keeps the previous one's values.

| block | fill_forward | fields | components |
|---|---|---|---|
| period | yes | one untagged list | list-based stress packages |
| period | yes | tagged list | OC (`output`) |
| period | yes | tagged arrays + tagged `aux` list | G/A packages, `utl-spca` |
| period | yes | one untagged string | `*-sto` |
| time | no | one untagged array | `utl-tas` |
| solutiongroup | no | tagged integer + untagged list | `sim-nam` |
| continuous | no | one untagged list, record header | `utl-obs` |

## Size and speed

The branch is +405 code lines: basic loader and egress about +30 together,
the typed loader about +360. With the basic loader, load and write didn't
regress beyond noise and peak memory is within ±5% (baseline in
[discussion #55](https://github.com/modflowpy/pyphoenix-project/discussions/55#discussioncomment-18978194),
harness in `benchmarks/`). Cold start went from 0.21 s to 0.26 s: the
stored DFNs plus building codegen's spec for `attr_names`. The typed
loader's numbers are in [`loader-comparison.md`](loader-comparison.md):
1.25× slower, up to 1.8× the memory, and stricter on errors. So basic is
the default and typed the opt-in, and deleting either is its own change.

## devtools follow-ups

- Extend `Block._check_field_order` to untagged fields of any type (at
  most one per block, and last), so the converter can rely on it.
- Make `_leading_tags`/`_is_dynamic_key` public (a `Field.tags` property).
  flopy4 wraps them in `spec.py` until then.

## Later

Each its own change.

- **Deleting a loader.** Deleting basic takes the stored DFNs with it, once
  egress reads the classes' fields. At stake: typed is ~360 code lines,
  ~1,300 with grammar generation and templates, plus 6,581 lines of
  generated grammars; basic is ~450.
- **Attribute names at sync time.** `spec.attr_names` builds codegen's
  spec of each class on first load, most of the cold-start gap. Sync could
  store the names, as it stores the DFNs.
- **The basic loader reads a number-like string as a number:** IMS's
  `rclose_option` written `50000.000` loads as `50000.0`. It's
  `test1001_Peterson`'s one difference under the typed loader.
- **An aux variable named like a field:** the typed grammar parses an aux
  named RECHARGE as the field. No corpus file does it.
- **A TAS time's array isn't recorded in `ArrayIO`**, so its read options
  aren't kept on write.
- **`test060_gms_ets`** loads under neither loader.
- **Short arrays load** under both. An array with fewer values than its
  shape keeps them, or with `LAYERED` is filled by repeating them. It
  should raise.
- **Load errors don't name the file.** Typed gives a line and column;
  basic neither.
- **The basic loader is lenient where MF6 isn't:** a missing `END` reads
  the next `BEGIN` as an unknown option, and a wrong-typed computed field
  (`MAXBOUND two`) is ignored.
- **The typed loader's memory:** 1.8× basic's peak on
  `test016_Keating_dev` and 1.7× on `test045_lake4ss_dev`.
- **Developer-mode fields.** The corpus uses `DEV_*` options the classes
  don't have, so both loaders warn and drop them. `sync` has a
  `developmode` option since #522; which mode the checked-in classes use
  is open.

The pre-refactor round-trip survey (load → write → reload over 239 corpus
models) found ten issues, all fixed on develop first: ISO datetimes, float
precision, model subdirectories, trailing tokens, single-name `AUXILIARY`,
aux-named G/A arrays (devtools #371), repeated `TS6` (devtools #368),
TAS-sourced period arrays (#413), ungenerated packages, quoted strings
(#462).
