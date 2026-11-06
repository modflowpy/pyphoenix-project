# After the DDL export: next steps

Written 2026-11-05, when [ddl-export.md](ddl-export.md) finished. Results are in the slice's
README (devtools' `ddl-slice` branch, local only).

## Where this leaves us

**A relational model is the right way to think about MF6's constraints, and a good way to
check them, but SQL is too verbose to be the spec.** That's a judgement, and steps 5 and
7 below are what could overturn it.

- **The model holds.** Union records are sparse tables, SPC vs. SPCA is a key kind, and each
  period regime in the slice is one view. The rules reject no valid model in 260 corpus models
  and 49 built ones, and agree with MF6 on 128 of 131 changed or baseline copies.
- **It finds things.** Three MF6 memory or input bugs, two flopy4 load bugs, an invalid corpus
  model and DFN errors. `keys.py` never caught anything the rules missed.
- **The text is large.** About 1,900 lines for roughly 30 of 145 components, keeping only
  what the rules read. Much of the 62% declared share comes from copying a dimension into each
  child row, which the DFN says in one line.
- **Views can fail silently.** A bad join reports "clean", and did twice in stage 3. The same
  case mistake in a foreign key was reported at once.
- **It strains on** arrays (64 million rows on Biscayne), geometry and run-time state.

So the working proposal ([factoring.md](factoring.md) has the rule for what stays out of the DFN):
the DFN stays the source, with relational meaning. The DDL is
generated from it where possible, with a short registry of named rules for what stays a view.
SQL is the checking target and test harness, and not what people maintain.

**What we don't know:** whether DFNs can generate propagated keys and period regimes, and how
the rules do on models they haven't seen. The rules were corrected after seeing failures, so
"no false alarms" is in-sample.

## Steps

In order. 1 and 2 are small and don't depend on anything. 3 and 4 are what development needs
next. 5 and 6 tell us whether to trust the slice, and 7 tests the DDL proposal.

### 1. Fix the loader bug (flopy4)

`trailing-text-load-fix.md` in the main checkout has the one-line regex change and a test. It's
silent data loss, so it goes first.

- [ ] Apply the fix and the test
- [ ] Rerun `test021_twri` through the slice, since its recharge has been missing from the
  export
- [ ] Decide on a warning when the trim removes text, and on text between blocks. Both are
  separate from this fix

### 2. Report what we found to its owners

Nothing has been filed.

- [ ] **MF6:** `gnc-numgnc-check-fix.md`, `obs-boundname-overrun-fix.md` and the earlier
  `spc-maxbound-check-fix.md`, in the MF6 checkout. All have tested fixes, and need CI
- [ ] **DFN, before parameters:** `dfn-fixes-from-slice.md` in the devtools checkout lists them in
  order. First `obs-boundname-when-fix.md`, then `maw-dfn-fixes.md`, OC's `format` and DISU's
  `IDOMAIN`. These are fixes to make, not only to report
- [ ] **DFN:** whether LAK's `iconn` key should stay scoped to the lake. MF6 counts across the
  package, so the key is stricter than MF6, and arguably more right. MAW's `icon` is the same
- [ ] **flopy4:** `oc-format-load-bug.md`, which is the one model that doesn't load
- [ ] **flopy4:** `keys.py` doesn't check OBS ids at all, and stayed silent on 22 broken copies
  that MF6 rejects. This belongs with binding navigation (step 4)

### 3. The parameter syntax sketch

Done: [parameter-sketch.md](parameter-sketch.md). Moved up from after the SQL work on 2026-11-05,
since it's what bears on development now. Keep it, though it comes out about the same size as what
it replaces, and what it buys is coverage. `when` can test a parameter. One decision is open there.

- [ ] Put `[params]` in the schema and migration on a devtools branch, after the DFN fixes in step 2

### 4. Binding navigation, and one conversion

Steps 5 and 6 of the overview. This is the real test of the sketch: if `Spc.target`,
`Mvr.model1` and `Obs.target` don't all come from one resolver, the construct isn't what it
claims to be. Two notes from the export:

- `keys.py` can check OBS ids once `Obs.target` exists.
- RCHA is much more common than the plan thought, at 92 packages in 87 models, and
  `v_rch_rate` has now run on real data, so RCHA ↔ RCH has a test bed. Its static part stops at
  `FIXED_CELL`: without it, MF6 moves recharge to the highest active cell at run time.

### 5. Run the rules on models they haven't seen

The missing number. Freeze `schema.sql`, `rules.sql` and the exporter at a commit, and don't
touch them until the first run is sorted.

- **Models:** `modflow6-examples` (7 built, 76 scripts), and MF6's autotests beyond the 23
  modules already used (457 in all). Prefer those with components the slice models but the
  corpus lacks. Others only count as far as their package rows.
- **How:** `export/build_autotest_models.py` and `run.py`. Run `mf6` on each first, and only
  valid models count.
- **Report:** models run, and how many rule hits on valid models, sorted by the table in
  `ddl-export.md`. Do that before fixing anything.

**Fails if** more than 2% of valid models are wrongly rejected by a rule, or more than one rule
is wrong. Stage 2 and 3's first runs found about four rules too strict, on about 300 models.

**Predictions, written before looking:** a rule or two is too strict, most likely on OBS types
the 6.7.0 catalog lacks, or on SPC. There are one or two exporter bugs in input forms not yet
seen. No new sum type.

### 6. Stop views failing silently

Two silent failures in one stage is too many to leave to care. This is worth doing even if the
slice is never used again, since it's a lesson for any checker built on it.

- [ ] Make every model and package name column `COLLATE NOCASE`, so the whole class of case
  mistake goes, rather than fixing joins one at a time
- [ ] Test every `r_*` and `w_*` view on a real model's data, not only on the fixture. A view
  with no broken copy that fires it gets reported. Today, each view's test uses the fixture, and
  the broken real models fire only some of the views
- [ ] Report a view that has rows to apply to, and whose join finds none

**Done when** the report lists each view as fired on real data, or as untested, with a reason.

### 7. Try generating one package's DDL from its DFN

The test of the proposal. Extend `gen_catalog.py` to write the tables for two packages:
**WEL**, as the plain case, and **MAW**, which has scoped keys, a union, `when` and propagated
dimensions.

- Generate the tables, keys, CHECKs and propagated columns.
- Run `test_slice.py`'s rule tests for those packages against the generated DDL.
- Count three things: constraints generated, constraints that needed a new DFN field, and
  constraints that had to stay by hand.

**Fails if** more than a quarter of those packages' declared constraints stay by hand, or the
DFN needs a construct used only to serve generation. Then the DFN isn't enough, and the choice
is between a richer spec language and giving up on generating.

**Predictions, written before looking:** keys and ranges generate easily. Propagated columns are
mechanical once a dimension's owner is known. Period regimes need a new field, since nothing in
the DFN says "snapshot" or "delta". Row CHECKs like `strt >= bottom` have no home in the DFN.

[parameter-sketch.md](parameter-sketch.md#why-this-isnt-name-again) says how parameters become
columns, so this can start from that.

### 8. Post

[Step 7 of the overview](overview.md#plan) said to post after steps 3 and 4 there, which are now
both done. There's a draft for discussion, `discussion-relational-results.md` in the main
checkout, which predates the sketch and doesn't cover its results. The slice's branch needs pushing before the post can link to it.

## Not doing, unless something changes

- **The rest of the slice.** 22 audited rules are unmodelled, mostly on components outside the
  slice. Covering all 145 components by hand is the opposite of the proposal.
- **The grid array regime.** It's H2b's last open case, and worth doing only if step 7 needs it:
  the exporter records only a `package` row for CHDG and WELG.
- **Array storage.** A row per value is wrong at Biscayne's size, but nothing needs a decision
  until a connector does.
- **A database connector.** See [ddl-export.md](ddl-export.md#where-this-could-lead). It needs
  a lossless schema, which also depends on step 7.
- **Merging the slice.** It stays research. If step 7 works, what's kept is the generator and the
  harness, and not the hand-written DDL.

## What would change the conclusion

- **Toward SQL as the spec:** generating fails (step 7), and a richer DFN looks worse than the DDL
  it would replace.
- **Away from relational checks altogether:** the rules do badly on unseen models (step 5), and
  fixing them means reading the Fortran for each one. That would show a hand-kept rule set can't
  stay honest, whatever its language.
- **Away from generating:** so few packages share a shape that the generator is mostly special
  cases.
