# Running the DDL slice on real models

Working plan, written 2026-11-05. Stage 1 is underway; results are in the slice
README. It carries out "a flopy4
counterpart" under [step 3 of the overview](overview.md#step-3-the-ddl-slice).

The DDL slice has only ever run on a hand-built fixture. This loads real models
with flopy4, exports them into the slice's schema, and runs its rules.

## What this can and can't show

MF6 accepts the corpus's models, so a rule firing on one is either a bug or a
discovery. That makes this a test for **false alarms**:

- Do the rules wrongly reject valid models, and which ones?
- Do constraints added on assumption hold? The main one is "an entry must be in
  an active cell", which the audit labelled but nothing has tested.
- How often do the warnings fire?
- Are the views usable at scale?
- Does `keys.py` agree with the rules?

A clean run doesn't show that the rules work. Only the slice's mutation tests
show that a rule rejects bad data, and `test_slice.py` stays the evidence for it.
Anything the loader drops is also invisible here, and a loader bug looks like a
rule violation.

## Picking this up

- **The slice:** worktree `/Users/wbonelli/dev/modflow-devtools-ddl-slice`, branch
  `ddl-slice`, in `research/ddl-slice/`. Read its README first. It's at `7bbaaa49`,
  on `a1468117`, and the branch is local only, not pushed.
- **Where the code goes:** `research/ddl-slice/export/`, with no changes to flopy4.
  That makes a devtools branch import flopy4, which is fine for throwaway research.
  Don't merge it as is.
- **How to run:** from the flopy4 repo, so flopy4 and `modflow_devtools` come from
  its environment:
  `pixi run -e dev python -m pytest <slice>/test_slice.py -p no:cacheprovider -p no:benchmark --rootdir=<slice> -c /dev/null`.
- **DFNs and MF6:** devtools `a1468117`, flopy4's pin. MF6 source
  `/Users/wbonelli/dev/modflow6` at `0dd9ed1784`. `bin/mf6` there is `1469b358b9`,
  and `_ci_debugopt/src/mf6` is a `-fcheck=all` build of `7f69b525e9`.
- **Don't** fetch, pull, push or post without asking.
- Tick "Status" below, and record results in the slice README.
- Check in with the user after stage 1's first full run.

## Decided

- SQLite with `STRICT` tables and views for what can't be declared
  ([overview](overview.md#step-3-the-ddl-slice)).
- `<=maxbound` is what's valid, and `(package, period, position)` is what an id
  means. So `w_mvr_id_unaddressed` is a warning, because that mover moves no water,
  and `w_spc_bound_unset` warns about a bound with no value, because it gets zero.
  A value for a bound not in this period's list doesn't warn. See the slice README.

## The corpus

`modflow_devtools.models`: 261 models, 242 in `mf6/test` and 19 in `mf6/large`.
`KNOWN_PASSING` in `test/mf6/test_mf6_load_all_models.py` lists 260 as loading.

Models per component, by file extension in the registry, so approximate:

| Component | Models | Component | Models |
|---|---|---|---|
| CHD | 194 | MVR | 24 |
| RCH (`.rch`) | 114 | MAW | 24 |
| WEL | 92 | DISV, DISU | 21 each |
| OBS | 76 | GWF-GWT exchange | 8 |
| LAK | 44 | SSM | 6 |
| SFR | 31 | RCHA (`.rcha`) | 3 |
| GNC | 28 | GWF-GWF exchange | 2 |

Among the MVR models: SFR 15, WEL 14, LAK 11, GHB 10, MAW 7, UZF 6, DRN 2, RIV 1.

**None has SPC, SPCA, LKT or SFT by extension,** so those rules can't be tested on
this corpus. Look for models in `/Users/wbonelli/dev/modflow6-examples` (not checked
yet), or generate some with the MF6 autotests that use SPC
(`test_gwt_spc_ts.py`, `test_gwt_ssm*.py`, `test_gwe_ssm*.py`).

## What a loaded model looks like

Checked by loading `mf6/test/test001g_MVR_transient`,
`mf6/test/test051_uzfp3_aeET_lakmvr_dev` and a hand-written GWF-GWT model:

```python
workspace = copy_to(tmp_path, model_name, verbose=False)  # modflow_devtools.models
sim = Simulation.load(workspace / "mfsim.nam")            # flopy4.mf6.simulation
```

| Schema | Loaded form | Notes |
|---|---|---|
| `period` | `sim.tdis.nper` | |
| `model` | `sim.models`, each `.name` and class (`Gwf`, `Gwt`) | |
| `solution`, `solution_model` | `sim.solutiongroup`, each `Ims` with `.slnmnames` | position in the list is `pos` |
| `exchange` | `sim.exchanges`, class such as `Gwfgwt` | `.exgmnamea` and `.exgmnameb` hold **model objects**, not names |
| `package` | `model._children`: key is the name, value is the package | `.dfn_name` is the component. Default names look like `wel-1` |
| `aux_name` | `pkg.auxiliary` | |
| `list_block`, `bnd_entry` | `pkg._stress_period_data`, a dict of period to rows | keys are 0-based. An **empty block is `{1: []}`, and an absent block has no key**. An `ItemTable`, or a plain list when empty |
| `bnd_entry.node` | `row.cellid`, such as `(0, 5, 3)` | a 0-based tuple; needs the grid to become a node |
| `bnd_entry.rate`, `rate_ts` | `row.q`, or `TimeSeriesRef(name='pumping')` | check the type |
| `bnd_entry_aux` | `row.aux`, a tuple in `auxiliary` order | |
| `sfr_reach` | `sfr.packagedata` | `ifno` is 0-based. `cellid` is a tuple |
| `sfr_conn` | `sfr.connectiondata`, `ic=((1, -1),)` | **pairs of 0-based index and sign**: here `ic = -2` in the schema |
| `sfr_set` and arms | `Sfr.StressPeriodData(ifno=0, sfrsetting=Sfr.Inflow(inflow=25.0))` | the arm is the class of `sfrsetting` |
| `lak_set`, `lak_outlet_set` | rows are the arm itself, such as `Lak.Rainfall(lakeno=0, rainfall=5e-08)` | key on the row's class |
| `lak_lake`, `lak_outlet` | `lak.packagedata`, `lak.outlets` | `lakeout=None` means none |
| `mvr`, `mvr_package`, `mvr_row` | `mvr.packages`, `mvr._stress_period_data` | **ids are 0-based**. `mname` is `None` on a model's mover, so fill it from the owner |
| `ssm_row` | `ssm.fileinput`, `ssm.sources` | `Ssm.Fileinput(pname='wel', spc=Spc(...), mixed=False)` |
| `spc`, `spc_set` | `fileinput.spc`, not a child of the model | `.maxbound` keeps the file's value |

**Everything else is unchecked:** GNC, exchange data, OBS, RCHA, DISV and DISU. Look
at the loaded form before writing those. Add 1 to every index the schema treats as
1-based, including period keys.

## Known problems

**The declared `MAXBOUND` is lost on load.** On the list packages, `maxbound` is a
property computed from the longest list (seen on WEL, RCH and GHB): a WEL file with
`maxbound 3` and two wells loads as 2. `keys.py` has the
same limit (`_longest`). Since `MAXBOUND` is what's valid, `r_mvr_id_range` would
fire on a valid id above the longest list. Read `MAXBOUND` from the package's file
with a small parse of its `DIMENSIONS` block, and record in the results that the
loaded model can't supply it. This doesn't affect SPC, which keeps its value.

**The schema rejects valid models as it stands.** Stage 1 and 2 have to change it:

| Gap | Change |
|---|---|
| `bnd` allows only WEL and RCH, while MVR also targets GHB, DRN and RIV | Widen it to the list-based stress packages. Keep `bnd_entry`'s address columns (position, node, boundname), and leave the other packages' values out |
| `bnd_entry` requires a rate or a time series | Relax the CHECK for the other packages, and keep `entry_value_or_ts` covering WEL and RCH |
| `v_address`, `v_capacity` lack MAW and UZF, so a mover on them looks like a broken id | Add both. Sizes are in `pakmvrobj%ar` calls: MAW `nmawwells` for both roles, UZF `maxbound` for both |
| The catalog has 10 components | Generate `component` and `obs_type` from the DFNs, using `test_catalog_matches_dfn`'s mapping of key paths to kinds |
| `cell` requires `layer` and `cell2d`, which DISU lacks | Make them nullable, and decide what `v_ncpl`, `r_rcha_shape`, `r_spca_shape` and `v_rch_rate` mean on DISU |
| `rhk`, `man`, `ustrf` and outlet fields reject a time series name | Add `_ts` columns, as on `bnd_entry` |
| Grid array packages (WELG, CHDG) have no entry rows | Record only the `package` row at first, and note what that leaves out |

Update `test_slice.py` and `fixture.sql` with each change, and keep them passing.

## The harness

Declared constraints stop at the first failure, but a run has to report them all.

1. Connect with `PRAGMA foreign_keys = OFF`.
2. Insert parents first, row by row, catching `IntegrityError`. Record the rule (the
   constraint in the message), the model and the row, then carry on. This covers
   CHECK, UNIQUE and NOT NULL.
3. Then `PRAGMA foreign_key_check` gives the orphaned rows, by child and parent.
4. Then select from every `r_*` and `w_*` view.

A row rejected in step 2 makes its children look orphaned in step 3, so mark those
as consequences, not as separate findings.

Write one row per finding to `export/results.csv`: model, rule, kind (declared,
foreign key, view, warning), count, and a sample row. A model that fails to load or
export gets a row too, so nothing silently drops out of the denominator.

Time each model's export and views. `mf6/large` has a 751×751 grid, and
`v_bnd_state` cross-joins every period, so it may need indexes. Run `mf6/test` first,
and `mf6/large` with a timeout.

## Sorting the results

Every hit is one of these, and the results should say which:

| Cause | Action |
|---|---|
| Exporter bug | Fix it |
| Loader bug | Record it for flopy4, and exclude it with a note |
| Rule stricter than MF6 | Check the Fortran. Then fix the rule, or make it a warning |
| The model breaks a rule MF6 doesn't check | A real finding. Record it |
| The model is itself invalid | Run `mf6` on it to confirm, and exclude it |

Don't assume that the corpus all runs. Where the cause isn't clear, run `mf6` on
that model. Use the bounds-checked build too if an array overrun is possible, as
the SPC bug in `spc-maxbound-check-fix.md` in the MF6 checkout showed.

Then compare with `keys.py`: call `flopy4.mf6.keys.key_errors(pkg)` on each package
of each model, and explain each disagreement with the key rules. Their definitions
differ in known ways: `keys.py` uses the longest list where the rules use `MAXBOUND`,
and it checks rules at write time.

## Predictions, written before looking

- Most rules never fire, and those that do are mostly exporter bugs at first.
- `entry_cell_active` fires on real models. Nothing has established that MF6 rejects
  every entry in an inactive cell, so this is the likeliest declared rule to
  become a warning or be dropped.
- `r_sfr_ustrf` fires, because MF6 skips reaches inactive at the start and the view
  reads the input only.
- `w_mvr_id_unaddressed` fires on a few models, and on list packages rather than
  advanced ones. `MVR` on a list that changes between periods is unusual.
- `w_spc_bound_unset`, once there are SPC models, is noisy on extraction wells.
- `r_gwfgwt_grid` and the exchange rules hold.
- `mf6/large` needs indexes, and the views stay under a minute per model once they
  have them.

Record how each of these turned out.

From stage 2:

- `r_sfr_ustrf` fires: **wrong on the corpus, right that the rule was wrong.** It never
  fired, but its reasoning was off as well. MF6 skips inactive *downstream* reaches, not
  reaches inactive at the start, and it rereads the sum as statuses change.
- `w_mvr_id_unaddressed` fires on a few models, on list packages: **held,** though on
  one model of 24, not a few. The cause is a WEL list emptied by blank blocks. Only 14
  of 1,374 mover ends are on list packages at all.
- "Mostly exporter bugs at first" was wrong again. No exporter bug showed up, and the
  only false alarm, `r_lak_belev`, was a bad rule.
- `MAW` and `UZF` sizes in `v_capacity` held: `r_mvr_id_range` is clean on all 687 rows,
  whose ends include 626 on UZF and 20 on MAW. Broken ids on real models were only tried
  on SFR and LAK.

So far, from stage 1:

- `entry_cell_active` **was wrong.** It never fires, and MF6 rejects these entries
  when run (`BoundaryPackageExt.f90:694`). It stays a declared rule, for list input
  only, since array input drops inactive cells silently.
- "Most rules never fire" holds so far, but 31 of 40 views had no data yet.
- "Mostly exporter bugs at first" was wrong: there were no rule hits to sort.
- `r_gwfgwt_grid` holds on 5 exchanges in `mf6/test` and 3 in `mf6/large`. The other
  exchange rules await stage 3.
- "`mf6/large` needs indexes" **was wrong.** The 751×751 grid took 0.08 s. Entries were
  the cost, through a bad join order in `v_bnd_state`: 125 s on 1.28 million entries,
  and 0.95 s once a `CROSS JOIN` fixed the order. "Under a minute" holds easily.

## Stages

Each answers something on its own, so it's fine to stop after any of them.

**Stage 1: binding lists, grid and list-based stress packages, on the whole corpus.**
The most data for the least mapping, and it tests the active-cell assumption first.

- [x] Widen `bnd`, generate the catalog, make `cell` handle DISV. DISU is deferred:
  those models are recorded as `deferred`, and their rule meanings are undecided
- [x] Read `MAXBOUND` from the file
- [x] Exporter and harness
- [x] Run on `mf6/test` and sort the results. No rule fired; 9 of 40 views had data
- [x] Check in with the user
- [x] `key_errors` comparison so far. No errors over 3,438 components and
  1,548,123 key values across both corpora, but it barely overlaps with stage 1's
  rules, so the rule by rule comparison waits for stage 2
- [x] `mf6/large`, with timings. 17 checked, 2 deferred, no rule fired over 7.75
  million entries, and every model's views take under a second

**DISU, brought forward from "deferred", before stage 2.** 19 models. Decided: `layer`
and `cell2d` are null together; `v_ncpl` has no row for DISU; RCHA or SPCA on DISU
is a rule of its own (`r_array_input_disu`); `v_rch_rate` is unchanged; `idomain`
above 1 is a rule, as MF6 has it, not as the DFN says; and the export is full, with
connections, vertices and plan rows, which DISV shares.

- [x] Export DISU and rerun. No rule fired on the 19 models, or on the rest of the
  corpus, and MF6 agrees with the rules on 18 changed copies of a small model. The two
  `test1002_biscqtg` models with 17.9 million list rows take 300 s and 7 GB. The DFN's
  `IDOMAIN` text is wrong, and `JA`'s order within a cell can't be expressed

**Stage 2: MVR and the advanced packages, on the 24 MVR models and then all SFR and
LAK models.** This answers the mover question with real data.

- [x] SFR, LAK, MAW and UZF, with `_ts` columns and the union arms
- [x] MVR, for models and exchanges
- [x] Count how often `w_mvr_id_unaddressed` fires, and why. One model of 24, 160 ends:
  wells named by a mover in periods after an empty WEL block
- [x] `r_sfr_*` and `r_lak_*` sorted. No rejection of a valid model is left. On the way,
  `r_lak_belev` and `r_sfr_ustrf` were stricter than MF6 and got fixed, `r_uzf_vert_area`
  went, and `r_lak_telev`, `r_sfr_div_ustrf` and `r_uzf_cell_area` were added
- [x] Rule by rule comparison with `key_errors`, on 54 broken or baseline copies, which
  MF6 and the rules agree on. It reports 6 of them, and a rule fires on all 6

**Stage 3: GNC, exchanges, OBS, SSM and SPC.**

- [ ] Look at the loaded forms first (see above)
- [ ] RCHA values (`rcha_value`), for `r_rcha_shape` and `v_rch_rate`, alongside SPCA,
  which needs the same array form
- [ ] GNC and exchange data
- [ ] OBS, widened past WEL, including `id2`
- [ ] SSM, and whether `flow_mname` resolves
- [ ] Find or generate SPC, SPCA, LKT and SFT models, then run those rules

**Afterwards:** update the slice README's results, this plan's predictions, and H1,
H2b and H3 in the [overview](overview.md#hypotheses) if real data changes them.

## Where this could lead

Not part of this plan, and not to start before stage 3, which tests the schema's
addressing model harder than anything so far.

The harness already loads a simulation into a real, if temporary, SQL database. That
could be a precursor to a connector that loads and writes simulations to and from
SQL in flopy4, and perhaps one day in MF6. The appeal over files is checking a
simulation before it runs, and querying across packages and periods.

What a connector needs that the slice doesn't have:

- **A lossless schema.** This one keeps only what the rules read. CHD, GHB and the
  other list packages have no values, and auxiliary values in package rows, solver
  settings, NPF and STO arrays and most options are missing.
- **A generated schema.** Covering every component by hand is too much to maintain.
  It should come from the DFNs, as `catalog.sql` does. Whether the DFNs say enough to
  generate propagated keys and period regimes is an open question.
- **A decision on layout.** The schema drops blocks, `JA`'s order within a cell,
  external files, `OPEN/CLOSE` and comments. A connector can keep a model's meaning
  without preserving its files, but users may expect otherwise.
- **Array storage.** A row per value works for tests. Gridded arrays over many periods
  need something else, such as blobs or Parquet alongside, and that choice shapes the
  design.

**First test: a round trip.** Export a package to SQL, rebuild it from the rows, write
the input, run `mf6`, and compare heads and budgets with the original. Start with the
packages the schema nearly covers. The corpus and harness already exist, and what
fails shows what the schema loses.

**MF6 reading SQL directly** is ambitious, but maybe less so than it sounds. SFR and
MAW already read from an `input_mempath`, so a different loader could in principle
fill that memory without touching package code. UZF still reads from the file parser,
so that move isn't finished. It would add a SQLite dependency to the Fortran build,
which is the MF6 developers' decision. Much of the benefit may be available without
it, since flopy4 could write ordinary input files from the database.
