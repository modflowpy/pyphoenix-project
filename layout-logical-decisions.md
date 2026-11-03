# Layout vs. logical: a rule for the MMP data questions

Written 2026-11-03 against `develop` (`8d25e4b7`). Status: **proposal.**
Several open MMP issues are about the same thing: how far flopy4's object
model should mirror MF6's file format, and where it should present the
underlying data instead. This doc states one rule for that, from the #287
work, and applies it to each issue. It feeds Track B and Track C of
`docs/dev/mmp-plan.md`.

The research behind the rule is in the working notes for discussion #287
(`option-classification-results.md`, `constraint-audit-results.md`,
`discussion-287-directions.md`; not on this branch yet). The parts this
doc needs are summarized below.

## The rule

### Three levels

MF6 input can be described at three levels:

- **Layout**: how the file writes things down. Blocks, keywords, arrays
  vs. lists, `CONSTANT`/`INTERNAL`, `LAYERED`, unit factors.
- **Logical**: what the data is. Tables, columns, keys, and the settings
  that change what the model computes.
- **Runtime**: MF6's memory. Its own layout, with solver artefacts.

### Option labels

Each of the 224 option names in the DFNs got a label by hand:

| label | count | examples |
|---|---|---|
| logical | 121 | `MOVER`, `SIMULATE_ET`, `AUXMULTNAME`, `SURF_RATE_SPECIFIED` |
| output | 82 | `PRINT_INPUT`, `SAVE_FLOWS`, `*_FILEOUT` |
| layout | 20 | `READASARRAYS`, `STORAGECOEFFICIENT`, `K22OVERK`, the unit factors |
| mixed | 1 | CSUB `HEAD_BASED` |

The split is clean: no layout option is triggered by, or triggers, a
logical constraint. The only crossings are conditions on where a layout
conversion is defined, e.g. RCHA can't express two rates in one column.

### Derivation

Some options declare a rule, "this quantity is computed from those". Each
such option is either:

- **static**: every input is fixed once written, so storing the result
  loses nothing (`STORAGECOEFFICIENT`, `K22OVERK`, the unit factors);
- **dynamic**: an input can change during the run (a time series, TVK,
  model state), and MF6 re-evaluates the rule each time it's used
  (`AUXMULTNAME`, `AUXDEPTHNAME`, TS/TAS, `LOCAL_Z`).

No layout option is dynamic. 14 of the 20 layout options are static
derivations.

### What it means for flopy4

1. **The object model holds input as given.** Layout choices stay in it:
   `Rcha` is its own class, `STORAGECOEFFICIENT` is an option, a constant
   stays a constant. This is what round-trip fidelity (FUNC-7) needs, and
   what flopy3 users expect.
2. **Logical forms are views.** Dense arrays, normalized tables, decoded
   values and conversions between layouts are computed from what's held,
   on request. They don't replace it.
3. **Dynamic derivations are never materialised silently.** A view that
   multiplies out `AUXMULTNAME` or evaluates a TAS says so in its name or
   arguments. Materialising one changes behaviour if an input later
   changes.
4. **Constraints follow their level.** A column that only means something
   under a logical option is absent without it, in the object model too.
   A column the file format requires positionally is the writer's
   problem.

## The issues

### #229: split STO by storage coefficient vs. specific storage?

Deltares suggests (a) two packages, or (b) separate `sc`/`ss` parameters.

- **Rule:** `STORAGECOEFFICIENT` is a layout option, a static derivation.
  The `ss` array holds SC instead of Ss, and MF6 converts with the cell
  thickness, which is fixed (gwf-sto: the keyword "indicates that the SS
  array is read as storage coefficient rather than specific storage").
  One quantity, two encodings.
- **Decision:** don't split the package (a). Two package types would
  turn an encoding into a type distinction, and every consumer of STO
  would have to handle both. Option (b) is fine as constructor sugar:
  `Sto(sc=...)` sets `ss` and `storagecoefficient=True`. Passing both is
  an error.
- **Migration:** accept. flopy3's form (`ss=` plus the flag) is unchanged.
- **MF6 side:** the issue's comment suggests raising it with MF6. There's
  no logical reason to split there either.

### #523: UZF placeholder values

UZF's period rows always have all seven value columns, but `pet`,
`extdp` and `extwc` only mean something with `SIMULATE_ET`, and `ha`,
`hroot`, `rootact` only with `UNSAT_ETAE`. Users write placeholders.

- **Verified in MF6** (`gwf-uzf.f90`): `SIMULATE_ET` sets `ietflag = 1`
  (line 487) and `UNSAT_ETAE` sets it to 2 (line 529). `uzf_rp` uses the
  ET columns only when `ietflag /= 0`, and the ETAE ones only when
  `ietflag == 2` (lines 691–693, 712–719, 764–768).
- **Rule:** both options are logical, so the columns exist only when the
  option is set. The fixed table is a layout. The keystring rows of the
  other advanced packages are another layout of the same relation:
  settings per feature per period, carried forward.
- **Decision:** make the six columns depend on their options, using the
  conditional fields from #473. Users don't pass them without the
  option, and get an error if they do. The writer writes a filler where
  the format needs one: the ET columns sit in the middle of the row, so
  without `SIMULATE_ET` the writer still has to put something there.
  Loading drops whatever filler the file has. No keystring redesign is
  needed, in flopy4 or MF6.
- **Migration:** deprecate passing the placeholders. Warn, and ignore
  them.
- **Check first:** whether the trailing `ha`/`hroot`/`rootact` can be
  left off the line when `UNSAT_ETAE` is off, or whether MF6's reader
  needs them.

### #345: normalize SFR `connectiondata`?

SFR writes one row per reach, with an inline array `ic` of length
`ncon(ifno)` from `packagedata`. LAK, MAW and UZF write one row per
connection. The issue suggests changing MF6's format to match.

- **Verified in MF6:** the sign of `ic` encodes the direction (DFN: a
  negative value means the connected reach joins at the downstream end).
  Every connection has to be listed from both ends, and MF6 checks it
  (`sfr_check_connections`, `gwf-sfr.f90:4416–4434`: "Reach n is
  connected to reach m but reach m is not connected to reach n").
- **Rule:** logically this is an edge table: one row per
  upstream→downstream pair. The file stores each edge twice, with a sign
  for direction, and `ncon` repeats a count of the rows. Both are layout
  redundancy that MF6 has to check.
- **Decision:** leave MF6's format alone. flopy4 holds `connectiondata`
  as given and offers a view:
  - a long table, one row per (reach, connection), like LAK's; and
  - optionally an edge table, one row per pair, with `ncon` and the
    reciprocity check derived from it.

  Whether a user can *build* SFR from the edge table, with flopy4 writing
  both directions and `ncon`, is a later, additive feature.
- **Migration:** none. The given form is unchanged.

### #226: packages without grid or time

`Ic(strt=0.0)` without a model now works, and stays a scalar (checked on
`develop`; the traceback in the issue is from xattree). What's left is
whether and when to expand it.

- **Rule:** the grid is a parameter supplied by the binding: a package
  gets its dims from the model it's attached to. A constant is a valid
  value as given, and `CONSTANT` is how the file encodes it. The issue's
  comment asks whether the user meant "write `CONSTANT`" or "my array is
  constant". Under the rule both readings hold: the value is held as a
  constant, and the writer picks `CONSTANT` because that's what's held.
- **Decision:**
  - Keep the value as given. Don't expand on attach.
  - When the package is bound to a model with a grid, give it a view with
    the grid's shape: the same expansion `dense()` does, named
    consistently with it (Track C).
  - Check shapes on attach, so an array that doesn't fit the grid fails
    there, not at write.
  - Leave `WriteContext` for overriding the encoding.
- **Shares machinery with #259 and #287 step 4** (navigation over the
  binding graph).

### #259: parent/child initialization

Top-down (`Dis(parent=gwf)`) and bottom-up (`Gwf(dis=dis)`) are both
supported, and the issue leans towards encouraging bottom-up.

- **Rule:** the parent/child relation is a binding row, as in the name
  file. Both styles create the same row, so neither is more correct.
  What matters is that the relation is held once, and both sides are
  views of it.
- **Decision:** keep both styles. Implement attach (`gwf.dis = ...`,
  `Dis(parent=gwf)`, `Gwf(dis=...)`) as one operation over the binding
  graph that updates both sides and runs #226's shape check. Design it
  together with #287 step 4 (`Spc.target`, `Mvr.models`, `Obs.target`,
  `Model.flow_model`), which needs the same graph.
- **Migration:** accept. flopy3's top-down style keeps working.

### Related: #240, #243

Fill values and time representation are representation questions.
Settle them in export phase 1 (Track C), below.

## Track C: the representation

`docs/dev/xarray-representation.md` already follows the rule for period
data: stored as given, `dense()` a view, TS/TAS values kept as named
references. It doesn't yet say how options appear. Add an Options section
in export phase 1:

| option label | in the representation |
|---|---|
| logical | data or attrs on the package node |
| layout | an encoding record, not data. xarray's `encoding` is the natural home, and the static derivations are the same kind of thing as CF's `scale_factor`/`add_offset`. But xarray drops `encoding` on most operations, so it may need to be attrs with a reserved prefix. Decide in phase 1. |
| output | not on the package's data. A separate node, or left out. |
| dynamic derivation | the rule, not its result: the aux variable carries its role (e.g. a multiplier). `dense()` doesn't apply it unless asked. |

`tas-interpolation-plan.md`'s step view is a dynamic-derivation view
under this rule, so it should be opt-in, and `from_xarray` should never
read its output back as input.

This is time-sensitive. The representation reaches testers at MMP, and
the xarray package plan's extraction criterion is a spec that has been
stable for a release or two.

## Track A: two kinds of equivalence

- **Round-trip** (FUNC-7, load → write → load): layout-preserving. A
  round trip that turns `READASARRAYS` into list input, or a `CONSTANT`
  into a full array, is a bug even if MF6 gives the same heads.
- **Cross-engine** (tier E's comparison of files written by flopy3 and
  flopy4): logical. Differences in layout and output options are
  expected. The option labels are the normalizer's rule table, rather
  than a hand-tuned diff filter.

## Not before MMP

The rest of the #287 work is off the gate. None of it changes what
testers write:

- the DDL slice and parameter syntax (#287 steps 2–3);
- conversions between layouts (RCH ↔ RCHA by densify and sparsify, step
  5), which are additive;
- logical annotations in the DFN schema, in devtools 2.0 if ready before
  the release candidates, otherwise in a later minor version;
- `source`/derivation metadata for modflowapi's memory catalog;
- the MF6 NetCDF format conversation.

## Open

- #523: whether MF6 needs the trailing ETAE columns when `UNSAT_ETAE` is
  off.
- #345: whether the edge view is worth having before MMP, or only the
  long table.
- #226: the name of the expanded view, decided with the accessor naming
  in Track B.
- Track C: `encoding` vs. prefixed attrs for layout options.
- Whether to post #287 before these decisions, so the Deltares
  developers who raised #226, #229 and #259 can weigh in on the rule.
