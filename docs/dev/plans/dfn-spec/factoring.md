# Where a fact belongs: DFN, classes, codec, checks

Written 2026-11-05, from a review of #544. This is the design rule for deciding where a
constraint or a piece of format knowledge goes. The aim is the least conceptual machinery and
code that still does the job. The terms (layout, logical, lens, binding) are the ones in
[overview.md](overview.md), and the constraint kinds (K1-K10, L) are from
[constraint-audit.md](constraint-audit.md).

## The factoring

```
DFN ──compile once──► classes ──► one read/write pair per field kind ──► text
                         │
                         └──► named checks over loaded components
```

Each part answers one question:

| Part | Its question |
|---|---|
| **DFN** | What does MF6 accept, for any client, in any language? |
| **Classes** | What can exist in Python? Their types and field metadata are the only schema the runtime reads. |
| **Codec** (`converter`, `codec`) | How is each kind of field written down? One read/write pair per kind, written once. |
| **Checks** | Is this combination of things sensible? Plain named functions. |

Three principles follow:

1. **Compile once.** The DFN is the source and the classes are its compiled form. If the runtime
   has to read the source again, or rerun part of the compiler, the compiled form is incomplete,
   and the fix is in codegen. We rejected the alternative of building classes from DFNs at import:
   readable generated source, type checking and IDE support matter to users.
2. **Variation is data, mechanism is code.** A fact that varies by component or field goes in the
   schema. Something uniform, or special to one or two components, is code, written once.
3. **Make it unrepresentable before validating it.** A rule the types make impossible needs no
   metadata, no validator and no error message.

## Where a constraint goes

Ask these in order, and stop at the first yes:

1. **Can the object model's structure make it impossible?** Then do that.
2. **Is it about how text encodes something?** Then it goes in the codec.
3. **Is it a declarative fact about one field or one table, true for any client?** Then it goes in
   the DFN, enforced by one generic validator per key rather than one per field.
4. **Otherwise** it's a named check, in code.

| Kind | n in audit sample | Home | Examples |
|---|---|---|---|
| K1 lexical / format | 10 | codec, with per-field facts (`index`) in the DFN | control records, `LAYERED`, ordering conventions |
| L lens domain | 6 | codec, which raises when a form can't be represented | binary lists with text columns, TAS on DISU |
| K2 type and domain | 27 | structure for types and enums; DFN for single-field ranges; named check for row comparisons | `Literal` words, `> 0`, `[0, 1]`; `THTS > THTR` |
| K3 shape and dimension | 10 | structure where the count can be computed; otherwise DFN `shape` | computed `maxbound`, array shapes |
| K4 conditional presence | 19 | DFN `when`, for names the component declares | `boundnames`, `surf_rate_specified`, a parameter |
| K5 option coherence | 14 | named check, for now | NPF's 7 rules, `UNIT_CONVERSION` |
| K6 keys and uniqueness | 12 | DFN `pk`, with one generic validator | `keys.py` |
| K7 referential | 21 | structure where it can be an object reference; otherwise DFN `fk` and `[params]` | children, `Exchange.model1`, `fk.path` |
| K8 co-occurrence and consistency | 19 | named check | MVR ⇒ MVT, same grid across an exchange |
| K9 temporal | 7 | named check | increasing periods, TS coverage |
| K10 structural / physical | 18 | named check, joining against the grid | `TOP > BOT`, SURFDEP ≤ thickness, acyclic SFR |

Sample counts show the sample only, not MF6 as a whole (see the audit's Limits).

## Stopping rule for the DFN

**No expression language in the DFN.** A predicate in a TOML string is a second programming
language that every consumer has to implement. Row comparisons, joins and option-coherence
predicates stay out of it.

**A new key has to earn its place.** It costs a change to the spec, the validator, codegen and the
runtime, against one function for a check. It should have many uses of one form, or a consumer
other than flopy4. Keys already in use with few uses deserve the same question when they next
change: `write_if_empty` (2), `allow_zero` (4), `dynamic` (7).

**Complete coverage is a non-goal for flopy4.** MF6 has 1,279 check sites and stays the authority;
the DFN fully expresses 20 of the 166 sampled rules. flopy4 has to reject what it can't represent
or round-trip. Beyond that, a check is a convenience, worth writing when failing early saves a
user real time.

### How this meets earlier decisions

- **`[params]` and `when` testing a parameter stand** ([parameter-sketch.md](parameter-sketch.md),
  decided 2026-11-05). A declared parameter is a fact a second consumer can implement from the
  spec, and 19 fields use it, so it passes the rule above. Its own test still applies:
  [step 5](overview.md#step-5-binding-graph-navigation). The review first advised against it,
  without having read the sketch; that advice is withdrawn.
- **The scope chain stops at declared names** (own options, dimensions, parameters). The sketch
  found that co-occurrence rules don't fit, so no implicit lookup among sibling components.
- **Item 4 of the audit's "Carried into the DDL slice"** (CHECK on the options row for K5) stays a
  fine relational reading, and a fine thing to generate in the checking target. It isn't something
  to author in the DFN yet. `requires` / `conflicts` is the likeliest key to qualify later.
- **The DDL proposal is compatible** ([ddl-next-steps.md](ddl-next-steps.md)): the DFN stays the
  source, and a short registry of named rules covers the rest. Whether a named rule is finally
  Python, SQL or both is still open there.
- **A DFN `when` and a derived option aren't in conflict.** The DFN says what the file requires; the
  class can compute the option that satisfies it (see below).

## Three structural changes

These remove constraints rather than enforce them. Not started, and not part of #544.

### 1. Variant flags become class constants

`readasarrays` and `readarraygrid` are settable booleans defaulting to `True`, in 8 generated
files. The class already is the variant, so `Rcha(readasarrays=False)` looks like an illegal state.
This follows [overview.md](overview.md#design-consequences): separate classes, discriminated at
load.

- [ ] Codegen emits them as class constants, and the writer writes them from there
- [ ] `is_grid_package` reads the constant, not the field's presence
- [ ] Decide what happens to a flopy3 or user script passing the keyword
- [ ] Check `readasarrays=False` really is rejected or meaningless first: it hasn't been tried

### 2. Options derived from what they describe

As `maxbound` already is, computed from the rows:

- **`boundnames`** from whether any row has a name. It covers 40 of the DFNs' 62 `when` uses. It's a
  logical option in [option-classification.md](option-classification.md), so deriving it doesn't
  change meaning, but a file with `BOUNDNAMES` on and no names wouldn't round-trip byte for byte,
  against "hold layout choices as given". Nothing can refer to a name that doesn't exist, so this
  looks acceptable, but it needs deciding.
- **`MODELNAMES`** from the binding: on when the component is bound under an exchange. Its pure
  encoding label and the sketch's two-way `when` both support this. It waits for binding navigation.

Both change the API. Removing a constructor argument needs a `legacy_kwargs` entry or a deprecation.

- [ ] Decide `boundnames`, including the round trip above
- [ ] `MODELNAMES`, after [step 5](overview.md#step-5-binding-graph-navigation)
- [ ] Look for others of this form before deciding the mechanism. `auxiliary` is the obvious
  candidate, and harder, since `aux` columns are named by it

### 3. One encoding per fact

STO's `stress_period_data` has both `Literal["steady-state", "transient"]` and
`valid=("steady-state", "transient")`, and `valid` also drives `_to_valid`, the case-insensitive
spelling converter.

- [ ] Codegen emits the `Literal` only, and the converter takes its words from the type
- [ ] Do the same wherever else `valid` and the annotation say the same thing (3 files use `valid=`)

## The test behind this

#544 as first written read block structure from stored DFNs and values from the classes, joined by
`attr_names`, which reran codegen's spec at load. To see whether the runtime needed the DFNs:

- **Comparison.** Class-only routing against the DFN's, across all 129 classes: 368 blocks and 1,223
  row keys. Block order and header kinds match everywhere. 1,219 keys matched, with stand-ins for
  the facts below; the other 4 were PRP's words and TS's alias.
- **Spike.** The DFN reads replaced by class introspection, and `flopy4/mf6/dfns` deleted, on nine
  test files including the round-trip suite: 740 passed and 241 snapshots matched, the same as the
  unmodified branch. The same 4 tests failed in both, for lack of an `mf6` executable.

Limits: that was nine test files, not the smoke suite or the whole suite, and nothing went through
MF6. The spike had stand-ins for the missing facts.

**What the classes lacked** was one fact, already in the DFN and dropped by codegen: which component
fields are untagged (STO `stress_period_data`, TAS's array, list rows that lead with a value, like LAK's). It's
`tagged = false` in the DFN, or derived for a list. The spike hardcoded two more that turned out not to
need emitting: the `NAME` alias was already on the class (`_aliases`), and a computed `maxbound` always
comes first in `dimensions`, which a test now holds.

So the classes were an incomplete compile, not the DFN an insufficient spec, and no DFN changes were
needed. The result:
[converter-simplification.md](../io/converter-simplification.md#classes-as-the-one-runtime-schema).

## What would change our minds

- A runtime need that field metadata can't express without restating a DFN block in a vocabulary of
  its own (the objection that ended `BlockSpec`).
- A non-Python consumer asking for a rule in the DFN. That's what the "second consumer" test is for.
- A family of named checks with one repeated form, which would be the case for a key.
- [ddl-next-steps.md](ddl-next-steps.md)'s steps 5 and 7 overturning the verbosity judgement, which
  would change what a named rule is written in, not where the rule belongs.
