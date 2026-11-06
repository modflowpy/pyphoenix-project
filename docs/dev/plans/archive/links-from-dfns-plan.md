# Child links from the DFNs

Replace `LINKS` in `flopy4/mf6/utils/codegen/make.py` with the component links devtools now migrates into the DFNs (`File.component`, `File.component_ftype`, modflow-devtools#379).

## Where we are

- `ncf-child` pins devtools at 42eea487 (#378 keyword aliases, #379 links).
- `field_link` reads `LINKS` only. It used to prefer a DFN link, but #379 links every file field, including to components flopy4 has no class for (codegen then failed on a missing `utl.tvk`).
- Every `LINKS` entry has an identical DFN link:

  | `LINKS` entry | DFN fields |
  |---|---|
  | `sim-nam` `tdis6` → `sim-tdis` | 1 |
  | `sim-nam` `models.mfname` → `model` / `mtype` | 1 |
  | `sim-nam` `exchanges.exgfile` → `exchange` / `exgtype` | 1 |
  | `sim-nam` `solutiongroup.slnfname` → `solution` / `slntype` | 1 |
  | `*` `ncf_filerecord.ncf6_filename` → `utl-ncf` | 8 |
  | `*` `ts_filerecord.ts6_filename` → `utl-ts` | 37 |
  | `*` `tas_filerecord.tas6_filename` → `utl-tas` | 3 |

  `LINKS` also makes `tdis6` required (`optional=False`); modflow6#3032 now does that in the DFN.

- DFN links not in `LINKS`:

  | Target | Fields | flopy4 class | Where |
  |---|---|---|---|
  | `utl-obs` | 52 | no | `obs_filerecord` in most packages |
  | `utl-tvk` | 1 | no | `gwf-npf` `tvk_filerecord` |
  | `utl-tvs` | 1 | no | `gwf-sto` `tvs_filerecord` |
  | `utl-spc` | 2 | no | `gw[te]-ssm` `fileinput` column (with `utl-spca`) |
  | `package` | 6 | n/a | model namefiles' `packages.fname` (model classes are hand-written) |
  | `gwf-mvr`, `gwf-gnc`, `gwe-mve`, `gwt-mvt` | 1 each | yes | exchange file records |
  | `utl-ats` | 1 | yes | `sim-tdis` `ats_filerecord` |
  | `utl-hpc` | 1 | yes | `sim-nam` `hpc_filerecord` |
  | `utl-laktab` | 1 | yes | `gwf-lak` `tables` column |
  | `utl-sfrtab` | 2 | yes | `gwf-sfr` `crosssections` column; period `cross_sectionrecord` |
  | `utl-spca` | 2 | yes | `gw[te]-ssm` `fileinput` column (with `utl-spc`) |

## Order

Delete `LINKS` first. A link becomes a child only if flopy4 generates a class for its target, so the deletion changes only ATS and HPC (step 2), and each class added later picks up its links on the next regeneration.

1. **Delete `LINKS`.** Done on `dfn-links`.
   - `_find_link` reads `component` and `component_ftype` from the DFN; `Link`, `LINKS` and `field_link` are gone.
   - A link is a child only if its target has a class (a generated module, or a hand-written base for an ftype-picked family) and its field is a file record, a list of them, or a namefile row. Files in rows with other data (LAKTAB, SFRTAB, SSM) stay paths until step 7.
   - `tdis6` is required in the DFN (modflow6#3032); regenerating from modflow6 `develop` keeps `tdis: Tdis`.
2. **File-record children with classes.** ATS and HPC became children with step 1; a Context now writes keyword children as `KEYWORD FILEIN <file>`, not namefile rows. MVR, GNC, MVE and MVT follow in step 4. No corpus model uses ATS6 or HPC6 (only `ex-gwt-adv-schemes` in the examples), so a synthetic test covers them.
3. **Generate TVK, TVS, SPC.** Done on stacked branches `tvk` → `tvs` → `spc`. NPF's TVK6 and STO's TVS6 are now children; rows keyed by a cellid before the arm keyword (`cellid K value`) needed an `item.py` fix. SPC is generated but SSM's column stays a path until step 7. No corpus model uses TVK/TVS; tests add them to `test001a_Tharmonic` / `test003_gwfs_tr`.
4. **Generate exchange classes.** Done on `exchanges`. `exg-gwfgwf`, `exg-gwtgwt` and `exg-gwegwe` are now generated, and their MVR, GNC, MVT and MVE file records are children.
   - Generated exchanges subclass `Exchange`, which replaces the hand-written `GwfGwt`/`GwfGwe`.
   - With MODELNAMES, MVR's optional `mname` columns come before its required ones. An `Item` can now declare `_columns` (DFN order), and those optional columns are present all together or not at all.
   - **Open:** the cellids in an exchange's EXCHANGEDATA take their width from the row length. That assumes both models have the same kind of grid; a DIS–DISV exchange would split its cellids wrongly. A fix would pass each model's dims. No corpus model has a mixed-grid exchange.
5. **Generate OBS** (own branch). 52 packages link to it.
   - **Repeating blocks.** CONTINUOUS repeats once per output file. Its header is the DFN's `Block.header` record `output` (`FILEOUT <file> [BINARY]`). OBS is the only block whose header isn't a number; PERIOD/TIME headers are numbers and stay `dict[number, ...]`.
     - Model the header after the devtools schema, with no fields the DFN doesn't have: generate a block class holding the header record's fields plus the block's list, giving `continuous: list[ContinuousBlock]` with `obs_output_file_name`, `binary` and the rows.
     - Rejected: `dict[str, list]` plus a `binary` set, because the set isn't in the DFN. Also rejected: inferring BINARY from `.bsv`, because it's lossy.
     - Needs work in four places. In the grammar, a string-record block header in place of `block_index`. In the transformer, the header record. In codegen, the header-plus-list block class. In egress, writing the header back.
   - **`id`/`id2` typed by parent.** The DFN types them as `string` (v2 dropped `numeric_index`). Each is a 0-based cellid tuple when the parent's rows are keyed by cellid (WEL/CHD/..., or model obs), a 0-based int feature number for LAK/SFR/MAW/UZF and their transport counterparts, and a `str` boundname otherwise.
     - Splitting the tokens needs the parent's `ncelldim` (from the dims passed to the child) and its kind. On a DISV grid `1 5` is ambiguous without the parent.
   - **Status.**
     - Header blocks are done on local branch `obs`, stacked on `exchanges`. Codegen generates `Obs.Output` (the header record, as an Item), `Obs.ContinuousBlock(output, continuous)` and `continuous: list[ContinuousBlock]`. The basic and typed readers keep each block's header; the writer writes `BEGIN CONTINUOUS FILEOUT <file> [BINARY]` / `END CONTINUOUS`.
     - All 115 corpus OBS files load and pass the typed grammar. Optional record keywords (`BINARY`, NPF's `RHS`/`DEWATERED`, the namefiles' `UNDER_RELAXATION`) are now named rules in typed grammars, so the typed reader keeps them.
     - Done. devtools #380 (merged) makes `id`/`id2` an untagged union of a cellid, an index and a boundname. Codegen gives an untagged union one column (`union=` metadata, arm kinds `cellid`/`index`/`string`). `Item.from_tokens` reads it: a non-number is a boundname. Numbers take the reading that uses the row's tokens, preferring the parent's arm: index under an exchange or a package with a `pk` column (LAK, SFR, MAW, UZF, CSUB, the GWT/GWE advanced packages), cellid otherwise. `Package.load(parent=...)` carries the parent class. Tokens past the ids are ignored, as in MF6.
     - Regenerated with `--existing-only`: 30 existing packages and exchanges now have `obs: Optional[Obs] = child(...)`. Packages not generated yet (MWE, SFE, UZE, MWT, SFT, UZT, ...) link when generated.
     - Corpus sweep: every simulation loads; 75 OBS files, 860 rows, all tokens round-trip except test051's trailing notes (dropped, as MF6 ignores them). Smoke roundtrips pass.
     - Known limits: on DISV a 2-token CSUB cellid reads as two indexes (and on DISU, a 1-token cellid as an index); either way it writes back the same tokens. UZF's water-content depth isn't in the union: a whole-number depth reads as an index, and other depths stay floats. The DFN also allows a boundname for id2, so a stray trailing note on a row that has no id2 is read as id2.
   - **Model-level OBS** (in the name file's `packages`) becomes a child only with step 6 (model classes).
6. **Generate model classes** (own project). Independent of `LINKS`: the namefile `packages` links are already in the DFNs. Hand-written behavior (grid coercion, methods) moves to a `*_methods.py` mixin like `Simulation`'s; `packages` becomes a children dict keyed by `ftype`.
7. **List-column children.** Done on `list-children` (rebased onto develop with the OBS commits). A list's file column naming a component with a class holds the component: `Lak.Tables(ifno, laktab=Laktab(...))`, `Sfr.Crosssections(ifno, sfrtab=...)`, `Ssm.Fileinput(pname, spc=Spc | Spca, mixed)`.
   - Every SSM row says `SPC6`; the file's `READASARRAYS` option picks SPCA (`_disambiguate_ga_variant`, as for RCH/RCHA).
   - Row children are part of the parent's `_children` (named `tables0`, `fileinput0`, ...), so they get parents and are written with it. `__setitem__`/`__delitem__` and bottom-up `Laktab(parent=lak)` don't reach rows.
   - SFR's period `CROSS_SECTION TAB6 FILEIN` setting stays a path. No corpus model uses SFR cross-sections or SSM SPC6 files; LAK tables are in test042/test045.


## Later, separately

- Replace the cwd lookup for file children with a thread-local load context, like `WriteContext`.
