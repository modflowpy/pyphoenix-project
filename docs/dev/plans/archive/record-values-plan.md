# Accept plain values for every record field

Status: done (2026-10-08), branch `record-convert`. PTS's `no_ptc` was
left out: `sln-pts.dfn` is gone upstream, so `pts.py` is an orphan. The
narrow fix for TS6/TAS6 landed earlier on branch `followups` (`036ccbf`).

## Problem

A record field (a keyword and its values, e.g. TS6's `NAMES a b`) is
typed as its generated `Record` class. Passing anything else used to be
accepted and stored as given, and then the writer silently dropped it:
`Ts(time_series_name=["a"])` wrote no `ATTRIBUTES` block, and the name
checks raised `AttributeError`.

Two converters cover some record fields today, chosen by codegen
(`make.py`, where record fields are emitted):

- `Record.from_flag`: a keyword and options, all optional (NPF's
  `XT3D [RHS]`): `True` is the bare record and `False` leaves it out.
  5 fields.
- `Record.from_value`: a keyword and one required value (TS6's `NAMES`,
  `METHOD(S)`, `SFAC(S)`; TAS6's `NAME`, `METHOD`, `SFAC`). The value is
  the record's value, and a list value can be given as one element. 8
  fields, all in `utl-ts`/`utl-tas`. Added by the narrow fix.

## What's left

Seven record fields still take only the record. Anything else is stored
as given and written wrong, or not written:

| Field | Record's fields | Natural plain form |
|---|---|---|
| `gwf-oc.headprint`, `gwt-oc.concentrationprint`, `gwe-oc.temperatureprint`, `gwt-ist.cimprint` | `formatrecord` (nested) | the format string, `"COLUMNS 10 WIDTH 12 DIGITS 6 GENERAL"`, which `Record.from_tokens` already parses |
| `gwf-npf.rewet` | `wetfct, iwetit, ihdwet` | a tuple `(1.0, 1, 0)` |
| `sln-ims.rclose` | `inner_rclose, rclose_option` | a float, or `(value, "strict")` |
| `sln-pts.no_ptc` | `no_ptc_option` | the option, like IMS's `no_ptc` (which has `from_flag`; check why PTS's doesn't) |

To recount, walk every generated component's fields whose type is a
`Record` but not an `Item`, and group them by converter.

## Plan

1. **One converter for every record field**, `Record.convert`, replacing
   the per-shape choice in codegen. It takes:
   - the record, or `None`: kept;
   - a bool: `from_flag`'s rule, only where all fields are optional;
     otherwise an error;
   - a `str`: `from_tokens`, as for the OC print formats;
   - a tuple: the record's fields in order;
   - a mapping: the record's fields by name;
   - any other value, for a record with one field: `from_value`'s rule.

   Anything else raises `TypeError` and names the field. Never store an
   unconverted value. If codegen can't tell how to convert a record,
   it should still emit `convert`, so a bad value fails at construction
   rather than being dropped on write.
2. **Codegen** emits `converter=X.convert` for every record field. Keep
   `from_flag`/`from_value` as the helpers `convert` uses, or fold them in.
   Regenerate. Expect every record field's line to change.
3. **Write-time guard:** where the writer reads a record field, raise if
   the value isn't a `Record`, instead of skipping it. It's a backstop for
   values set after construction (`pkg.field = [...]` bypasses the
   converter unless `on_setattr` runs it; check what `Component` sets).
4. **Typing.** mypy ignores `field()`'s converters
   ([`mypy-converter-plan.md`](mypy-converter-plan.md)), so plain forms still fail type checks in
   user code until that plan lands. Do this plan first: it fixes runtime
   behavior, and the converter plan then makes the same forms
   type-check. Library code should keep building records explicitly
   (e.g. `Ts.from_series` builds `Ts.TimeSeriesName`) so it passes mypy
   either way.

## Tests

- Each plain form above round-trips: construct, write, load, compare to
  the record-built component.
- A wrong-shape value (a list for `rewet`, a bool for `rclose`) raises
  at construction, naming the field.
- Setting a record field after construction converts, or the write
  guard raises.
- Existing `from_flag`/`from_value` tests keep passing.
