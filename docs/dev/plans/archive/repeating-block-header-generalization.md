# Generalizing repeating-block handling via `Block.header`

**Archived 2026-10-19.** Partly adopted: codegen now reads `Block.header` (`make.py` ~1374, `filters.py` ~139) for repeating blocks and fill-forward. The full generic consumer sketched here wasn't pursued, and the doc's own conclusion was "not now".

Found while investigating whether flopy4's `utl-tas` support (self-sizing
arrays, [`dev3-migration-gaps.md`](dev3-migration-gaps.md)) could be simplified. It can't be
simplified in isolation, but the investigation surfaced something flopy4
doesn't currently use: dev3's schema already has a generic "this block
repeats, keyed by this header field" concept
(`modflow_devtools.dfns.schema.Block.header` / `.repeats`), richer than
legacy's bare `repeating: bool`. flopy4 doesn't consume it anywhere — not
even for PERIOD blocks, which hardcode the literal string `"period"` at
every call site instead. This doc sketches what a generic consumer would
look like. **Not a plan to implement now** — see "Is this worth doing" at
the end.

## What the schema already gives us

```python
class Block(BaseModel):
    name: str
    fields: dict[str, InputField]
    header: "InputField | None" = None

    @property
    def repeats(self) -> bool:
        return self.header is not None
```

Verified in the current dev3 snapshot (`~/dev/modflow-devtools/autotest/dfns/__snapshots__/v2.0.0.dev3/`):

- `gwf-rch.toml`: `[blocks.period.header]` → `name = "iper"`, `type = "integer"`
- `utl-tas.toml`: `[blocks.time.header]` → `name = "time_from_model_start"`, `type = "double"`

Both repeating blocks in the whole corpus (PERIOD and TIME — TAS is the
only non-PERIOD repeating block) already carry this. `header` gives the
dict key's *name*, *type*, and *description* — enough to drive parsing
generically instead of hardcoding per block.

## Current state: every hardcoded `"period"` (and TAS-equivalent) site

None of these consult `block.header`/`block.repeats`. All hardcode the
literal block name:

**`flopy4/mf6/utils/codegen/filters.py`**
- `has_period_block`: `"period" in component.blocks`
- `is_period_array`: `block_name == "period"`

**`flopy4/mf6/utils/codegen/make.py`**
- `_period_keystring_names`: `component.blocks.get("period")`
- `_build_block_property_specs`: skips `block_name == "period"` explicitly
- `build_component_spec`'s main field loop: four separate
  `block_name == "period"` branches (list field / keystring union / bare
  scalar / READARRAY array), plus the TAS-equivalent branch gated by
  `filters.is_readarray_field(f)` (name-matched, not block-matched)
- period dict-field assembly (`_stress_period_data`, `_readarray_period_fields`):
  hardcodes `"block": "period"` metadata and the `kper = iper - 1` 1-based→0-based
  convention

**`flopy4/mf6/converter/ingress/structure.py`**
- Pass 1's skip condition: `block_name.startswith("period")`, plus a
  separate `tar_block_prefixes` set built from `reader == "readarray"`
  metadata (TAS's parallel mechanism, keyed off field metadata rather than
  block name)
- Pass 3 (period): `block_name.startswith("period")`, splits on whitespace,
  parses `int(parts[1]) - 1`
- Pass 3b (READARRAY period): `f.metadata.get("block") == "period"`
- Pass 3c (TAS): separate pass entirely, parses `float(parts[1])`, no `- 1`

**`flopy4/mf6/converter/egress/unstructure.py`**
- `block_name == "period"` branch (two sub-cases: READARRAY ndarray, and
  Item-list dict), producing `f"period {kper + 1}"` keys
- Separate branch for `reader == "readarray" and isinstance(field_value, dict)`
  (TAS), producing `f"{block_name} {tval}"` keys — no `+ 1`, float not int

The PERIOD and TAS code paths are structurally the same shape (a block
that repeats, keyed by a header value, containing either an Item-list, a
keystring union, or a bare array) but are implemented as two unrelated,
independently-hardcoded passes.

## What a generic consumer would look like

**Codegen (`make.py`):** iterate `component.blocks.items()` and check
`block.repeats` instead of comparing `block_name == "period"` inline in
the field loop. For any repeating block, dispatch by its field shape —
same three cases already handled for PERIOD, generalized:

- Item-list field (with or without a keystring union) → `dict[<key_type>, list[ItemClass]]`
  (generalizes `_stress_period_data`/`period_arms`)
- Bare Array field → `dict[<key_type>, ArrayLike]` (generalizes
  `_time_array_series_fields` — this is what TAS already does)
- `<key_type>` comes from `block.header.type` (`int` for PERIOD's `iper`,
  `float` for TAS's `time_from_model_start`) instead of being implied by
  which hardcoded branch matched

**Ingress (`structure.py`):** one generic pass over `component.blocks`
where `.repeats`, replacing Pass 3/3b/3c: split `raw_lower` keys on each
repeating block's name prefix, parse the header token using the declared
header type, dispatch to item-list or bare-array parsing by field shape —
same dispatch already written, just triggered by `block.repeats` instead
of string-matching `"period"` or a `reader == "readarray"` metadata scan.

**Egress (`unstructure.py`):** the PERIOD branch and the TAS branch merge
into one "repeating block" branch, formatting `f"{block_name} {header_value}"`.

**The one genuine PERIOD-specific wrinkle:** MF6's PERIOD block header
(`iper`) is 1-based in the file, and flopy4 stores it 0-based (`kper`) for
Python-list-index convenience. That offset is an MF6/flopy4 convention,
not something `Block.header` encodes (TAS's `time_from_model_start` has no
such offset — it's used as-is). A generic consumer still needs a per-block
hook or metadata flag for this, not something inferrable from the schema
alone.

## What does *not* get simplified by this

`is_readarray_field`'s shape check (`Array.shape == []`) and the
`array_bare` writer path are about *shape ambiguity* — dev3 can't tell "a
plain self-sizing trailing-tokens field" from "a griddata-style field
whose own block repeats" by shape alone (see `is_array`'s docstring). That
is a completely separate problem from block-repetition and doesn't go
away if `Block.header` is consumed generically. See the companion
walkthrough on `just_data` for the related, but distinct, "no leading
field-name token" question.

## Is this worth doing

Not now. The entire MF6 corpus has exactly two repeating-block shapes
(PERIOD, TIME) — generalizing a mechanism that has exactly one non-trivial
consumer beyond the original is speculative. Worth revisiting if/when a
third repeating-block package shows up, or if the PERIOD-side hardcoding
itself becomes a maintenance burden independent of TAS.
