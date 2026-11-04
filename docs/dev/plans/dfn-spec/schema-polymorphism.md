# Schema polymorphism (#287) vs. component key roles (devtools PR #405)

How [discussion #287](https://github.com/modflowpy/pyphoenix-project/discussions/287)
relates to the component key roles of devtools PR #405 (designed in
devtools' `context-refs-plan.md`, "Slimmed scope"). They're related, but
different kinds of polymorphism. Both involve a supertype with
subtypes. They differ in what the subtypes are and what picks one of them.

## Two kinds of polymorphism

**#287 is variant polymorphism (a sum type).** One concept comes in several forms, and only
one of them is used:

- RCH or RCHA, EVT or EVTA, SPC or SPCA;
- structured grid or UGRID mesh;
- ASCII array input or NetCDF variables.

An option in the input decides which form applies (`READASARRAYS`, the grid type, `NETCDF`).
The question is "what shape does *this* thing have?" In Python this is a pydantic
discriminated union.

**Key roles are reference polymorphism (an interface).** MVR `id1` points at a row in
whichever package `pname1` names: WEL, LAK, SFR and so on. These packages aren't alternatives
to each other. They all exist at once, and each plays a role such as `mover_provider`,
`mover_receiver` or `bound`. A `[keys]` entry says "this component implements this role, and
this column is its key." The question is "which of the existing things does this row point
at?"

- In Python this is a Protocol or ABC, not a union.
- In relational terms it is a polymorphic association, with the role acting as a supertype
  key table (a polymorphic association, also called an exclusive arc, is one column that can
  reference rows in several different tables).

| | #287 variants | Key roles |
|---|---|---|
| Members | Alternatives: one is chosen per slot | All coexist; each referencing row picks one |
| What picks | An option in the same file, known when that file is parsed | A data value in another file (`pname1`), resolved across the simulation |
| Spec construct | Not designed yet (something like "variant of X when option Y") | `keys` plus fk `key` |
| Python | Discriminated union | Protocol, or a registry from role to implementers |

## Where they meet

### 1. The variant chosen decides which roles exist

Each variant is its own component and declares its own roles. In the devtools snapshots:

- `gwf-rch.toml` and `gwf-evt.toml` declare `[keys]` (`bound`), and with #406 so do SFR/UZF
  (`packagedata.ifno`), LAK (`<=nlakeconn`) and MAW (`<=ngwfnodes`);
- `gwf-rcha.toml`, `gwf-evta.toml` and `utl-spca.toml` don't.

That is correct, because array input has no `bndno` rows, so there is nothing for SPC to key
into. The two ideas therefore compose: variant selection happens at the component level, and
roles attach to components.

### 2. `KeySet.when` was a #287-style condition

The dropped `when` said "LAK plays `mover_provider` only when its MOVER option is on." That is
the same pattern as "this file must contain NetCDF variables only when `NETCDF` is set": a
part of the schema that turns on with an option.

We removed `when` from the spec and made it a consumer check. (Update: devtools #406
makes it the named rule `mover_enabled` on MVR `packages.pname`, so no consumer checks
remain outside the spec's rule registry. #395 has since made field `when` standard, so
`when` on key sets would reuse existing syntax, not add one-off syntax. See
`discussion-287-comment.md`.) That is right for now, because
it was the only construct needing its own syntax for one condition.

If #287 later adds a general way to say "this part of the schema depends on option X", the
MOVER check should move onto it. Keep one vocabulary for option-conditional schema rather than
growing a separate one for each feature.

### 3. Named rules and #287's NetCDF example are the same kind of constraint

The fk rules in #405 (`exchange_models`, `flow_model`, `ssm_package`) depend on context and
cross files. So does #287's third example, where the ASCII files decide which NetCDF variables
must exist.

The test agreed for #405 applies to both:

- static structure belongs in the spec;
- constraints that depend on the rest of the simulation are named rules or runtime checks.

Applied to #287's examples:

| Example | Kind | Where it belongs |
|---|---|---|
| List vs. layer-array vs. grid-array | Static structure | Spec: a variant declaration |
| Structured vs. UGRID mesh | Static structure | Spec: a variant declaration |
| ASCII drives NetCDF contents | Cross-file condition | Closer to a named rule or consumer check |

## Implications

- **flopy4 `keys.py`:** model each role as a registry mapping the role to its implementing
  components and key columns (the interface view), not as union types. Pydantic discriminators
  need a literal tag on the object itself, but the tag here (`pname1`) lives on a different
  row.
- **flopy4 object model for #287:** discriminated unions are still the right tool for the
  variants.
- **Spec vocabulary:** if #287 produces a spec construct for variants or option-conditional
  schema, check whether it can also express:
  - MOVER-on as a condition for role membership (the old `when`);
  - possibly some of the named rules.

  Don't add it to #405 now.

## Open questions

- Should variants be declared explicitly in the spec, for example `variant_of = "gwf-rch"`
  with the discriminating option? Today the relationship is implied by naming
  (`rch`/`rcha`, `spc`/`spca`).
- Would a variant-level construct let consumers check that a referencing component matches its
  target's variant? Example: SPCA must bind to RCHA or EVTA, not to RCH. Today that is a
  runtime check, if anything checks it at all.
- NetCDF/mesh polymorphism changes the dimensions of every array variable. Is that a variant
  of each component, or one simulation-wide parameter that changes field shapes? The second
  looks more like dimension polymorphism than a sum type.
