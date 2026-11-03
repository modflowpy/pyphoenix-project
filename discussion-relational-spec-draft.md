<!--
Draft for a separate discussion (not yet created). Cut from the #287
comment draft (discussion-287-comment.md). Link back to #287 when posting.
Background: ~/dev/modflow-devtools/relational-model-plan.md.
-->

## A relational view of the DFN spec

Most of the key metadata recently added to the DFNs is familiar from databases (see #287 for the broader context):

- scoped keys are composite keys;
- roles are supertype tables;
- `<=maxbound` is an implicit row id;
- `allow_zero` is a nullable fk;
- each rule is a view: a named subset of the target, mostly filtered by binding context (the exchange's two models, the paired flow model).

Union records are the only thing with no clean relational equivalent, since databases don't have sum types.

That raises a question: should we define the spec in two layers? A logical layer would hold tables, columns and keys. A layout layer would say how the MF6 text format writes them down: blocks, keywords, arrays and omitted columns.

Seen that way, much of #287's "functional equivalence" is a layout difference. RCH and RCHA are one logical relation, a rate per cell per period, written two ways. The ASCII/NetCDF choice is also mostly layout.

Candidate languages for the logical layer:

- **SQL DDL**: no sum types.
- **Frictionless**: no polymorphic keys or sum types.
- **LinkML**: inheritance might cover both.
- **A relational subset of our own TOML**, exported to one of the above.

### Open questions

- **Should the spec split into logical and layout layers**, and which language should define the logical one?
- **Should each rule be defined as a view?** The spec would be checkable, but it would grow.

### Proposed next steps

- **devtools**: hand-write SQL DDL for a slice of components that covers every hard case:
  - binding lists;
  - WEL;
  - RCH/RCHA;
  - SFR, LAK and MVR;
  - SSM and SPC;
  - GNC;
  - exchanges;
  - OBS.

  This tests whether every construct translates to tables and keys, whether the rule views are short enough to put in the spec, and which language fits.
- **flopy4**: export a simulation to SQLite/DuckDB, and write the key checks as SQL queries to compare with `keys.py`.
- **Variant conversion**: with a logical layer, converting between variants (RCH↔RCHA, structured→UGRID) becomes re-laying out the same data.
