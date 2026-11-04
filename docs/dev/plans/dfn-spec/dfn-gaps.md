# DFN and memory catalog gaps

**For MF6 and modflow-devtools developers.** Input rules that MF6
enforces but the DFNs don't state, and gaps in the DFN `[memory]` catalog.
Found by the [constraint audit](constraint-audit.md) and the
[option classification](option-classification.md), against the dev3
snapshots (schema `v2.0.0.dev3`) and MF6 `8aad7bc4a5`.

The audit sampled MF6's checks rather than reading all of them, so the
lists are examples of each gap, not complete inventories.

## Rules in Fortran that the DFN could state today

These need no new DFN syntax.

- **`when` on the MST arrays** (and their GWE counterparts):
  - `bulk_density`, `distcoef` and `sp2` only with `SORPTION`;
  - `decay` and `decay_sorbed` only with the decay options;
  - `sp2` only for Freundlich or Langmuir sorption. This one needs a test
    on the option's value, not just its presence.
- **`pk`** on SSM SOURCES `pname` (`tsp-ssm.f90:820`), MVR PACKAGES
  (`gwf-mvr.f90:917`), and the LAK/MAW/SFR "specified more than once"
  checks where they aren't already marked.
- **`valid`** for string enums that MF6 checks but the DFN only lists in
  the description:
  - SFR `cprior`;
  - LAK `claktype` and `couttype`;
  - MAW `condeqn`;
  - IMS `complexity`, `under_relaxation`, `no_ptc_option` and
    `rclose_option`.

## Rules in Fortran that need new DFN syntax

- **Numeric ranges.** The biggest gap by count: the "must be positive /
  in range" message shape alone has 165 sites, and the DFN has no numeric
  range key at all. A `range` or `min`/`max` key, with open or closed
  bounds, would cover `> 0`, `≥ 0` and `[0, 1]`. Comparisons within a row
  need an expression: `THTS > THTR`, `DTMIN < DTMAX`, `telev ≥ belev`.
- **Option conflicts and requirements.** A `conflicts`/`requires` key on
  options. NPF alone has seven such rules (`gwf-npf.f90:1715-1757`).
- **Block-level `when`.** `ANGLEDATA` only with `NON_VERTICAL_WELLS`;
  `DIVERSIONS` only when some reach has `ndv > 0`.
- **Required components and co-occurrence.** `multi = false` says "at most
  one", but nothing says "at least one": DIS in every model, IC and NPF in
  GWF, DFW in OLF. Nothing expresses MVR ⇒ MVT or LKT ⇒ LAK.
- **Dimensions across components.** SPC `MAXBOUND` must cover the flow
  package's bounds (`TspSpc.f90:347`).
- **Key kinds on roles.** MF6 enforces that SPC pairs with list packages
  and SPCA with array packages (`TspSpc.f90:360-380`). The DFN only
  implies it by naming. If a role stated the kind of key it uses (a bound
  number or a grid column), the ordinary foreign key check would catch a
  mismatch. See [overview.md](overview.md#h4-spcspca-pairing-is-a-key-kind-match).

## Rules only in the mf6io docs

209 hand-written rule-like sentences; 7 checked in detail.

- DISV vertices in clockwise order (`gwf/disv.tex`): not enforced.
- A TAS file can be associated with only one package (`gwf/tsi.tex`): no
  check found.
- LKT needs a corresponding LAK, and the advanced transport packages take
  their flow package's name by default (`gwt/sft.tex`, `lkt.tex`). These
  are enforced indirectly, through the name lookup (`gwt-sft.f90:206`).
- PRT and GWT through FMI need particular GWF output (`SAVE BUDGET ALL`,
  heads for all layers). FMI checks part of this (`tsp-fmi.f90:676-688`).
  The rest is a rule about another run's output.

## Checked late

Time-series coverage is checked only when a value is needed during a time
step (`TimeSeries.f90:552-601`), so a short time series fails partway
through a run. A spec could state it as "TS times cover the simulation
span, unless `extendToEndOfSimulation` applies", and a validator could
check it up front.

## Memory catalog

- **Probable error:** `iprpak.source = "save_flows"` in `gwe-ctp` and
  `gwt-cnc`. It should probably be `ipakcb`.
- **`bound` has no `source` in any stress package**, list variants
  included: there's no syntax for the multi-column mapping (value columns →
  `bound` rows). Array variants (`*A`, `*G`) also lack `source` on
  `nodelist`. A `source` expression language would need column lists, a
  cell mapping (cellid → reduced node), and an array → list projection with
  a layer index (`IRCH`/`IEVT`) or a NODATA mask.
- **Options with a clear runtime effect but no mapping:**
  - catalogued, but with no `source`: `auxiliary` (`naux`, `auxname_cst`
    in `gwf-chd`);
  - not catalogued at all (checked in `gwf-chd` and `gwf-dis`):
    `boundnames` (`inamedbound`), `auxmultname` (`iauxmultcol`), `mover`
    (`imover`), the DIS georeference variables (`xorigin`, `yorigin`,
    `angrot`), `fixed_cell`, `newtonoptions`, the solver options
    (`complexity`, `no_ptcrecord`, the ATS fractions), and the GWT/GWE
    `scheme`/`xt3d_*` options.

  The full list is the rows with a blank `memory` column in
  [options-labelled.csv](data/option-classification/options-labelled.csv).
- **Partial coverage:** the same option is mapped in some components and
  not others. `save_flows` 51 of 79, `print_input` 43 of 78, `print_flows`
  41 of 72, `length_`/`time_conversion` 3 of 5, `cvoptions` 1 of 2, and
  the OC file records.
- **Flags that change how a value reads.** Some options leave the stored
  value encoded and keep a flag: under `K22OVERK`, `k22` holds a ratio to
  `k11` (`ik22overk`); under `STORAGECOEFFICIENT`, `ss` holds a storage
  coefficient (`istor_coef`). The catalog should say so on the variable
  they qualify. Otherwise an API caller that reads or writes `k22` can't
  know what it holds.
- **No `settable` flag.** The catalog has `readonly` but nothing marking a
  variable as a model parameter an API caller may set, so there's no way
  to check which logical options reach one.
