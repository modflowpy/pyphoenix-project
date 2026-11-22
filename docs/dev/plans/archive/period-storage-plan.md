# Per-period storage for period arrays

Status: agreed (2026-10-05), against develop `82d2a99` (#406). Decisions are
recorded under "Decisions" below.

Implemented (2026-10-06) on branch `period-storage`, commit `3e8d527`, steps
1–4 together (not pushed). It differs from the plan in a few ways:
- Conversion happens in `Package._init_period_arrays` (replacing
  `_init_dynamically_named_arrays`), not as a per-field converter in codegen.
  The aux checks need `self`.
- Each period's array is flattened to the field's DFN shape, as griddata is.
  Before, a file loaded as `(nlay, ncpl)` while input stayed `(nodes,)`.
- Egress reshapes each period's array to the grid's layer shape. MF6's
  period-block reader failed on a 225-value layer written on one line.
- `attrs_to_dataset` stacks the given periods along `<name>_period`, so
  cleared periods survive the xarray round trip.
- Side effect: `test019_VilhelmsenLGR{,_nr}` now load (they xpass).

## Problem

Period array fields (WELG `q`, RCHA `recharge`/`irch`, …) hold one dense
array with an implicit leading `nper` axis. Periods and cells with no value
are filled with `FILL_DNODATA` (3e30). That one value currently means three
things:

1. **No stress in this cell.** This is MF6's own meaning: a grid package
   activates the cells that aren't `DNODATA`.
2. **This period wasn't in the file** and carries forward. Ingress pre-fills
   it (`structure.py:955`), and egress skips any period that's entirely
   `FILL_DNODATA` (`unstructure.py:306`).
3. **Fill value for integer arrays.** `irch`/`ievt` are stored as floats so
   they can hold 3e30, and the index conversion skips it (`unstructure.py:149`,
   `netcdf.py:273`).

Meanings 1 and 2 collide in grid packages: a period block that clears every
boundary can't be told apart from a period that isn't in the file. PR #380
works around this with an undeclared `reset_periods` attribute. Meaning 3 is
the `int-fill` problem.

## MF6 semantics (checked in `modflow6/src/Utilities/Idm/mf6blockfile`)

- **Grid packages** (CHDG, DRNG, GHBG, RIVG, WELG; `Mf6FileGridArray.f90`):
  - Every period block present in the file resets the boundary set
    (`reset` sets `nbound = 0`).
  - The block's first array decides which cells are active (the ones that
    aren't `DNODATA`). Later arrays, including aux, are read at those cells.
  - So a period is one unit: an empty block clears everything, and a
    missing block keeps the previous period.
- **Layer-array packages** (RCHA, EVTA, SPCA; `Mf6FileLayerArray.f90`):
  - A block resets only which arrays were read this period. Each array keeps
    its previous values until it's given again.
  - So carrying forward happens per array, and there's no "clear".

## Representation

Store each period array field as a dict keyed by 0-based stress period. The
dict holds only the periods the file gives:

```python
q: Optional[dict[int, FloatArrayLike]]                # {0: arr(nodes), 3: arr(nodes)}
irch: Optional[dict[int, IntArrayLike]]               # stays int, no sentinel
aux: Optional[dict[int, dict[str, FloatArrayLike]]]   # aux[kper][name]
```

- **Period is always the outer key**, for every period field including aux,
  as in list packages' `stress_period_data[kper]`.
- **Missing period:** no key. The previous period's values carry forward.
- **Cleared period (grid packages):** a key whose stress arrays are entirely
  `DNODATA`. Here 3e30 is MF6's value for "no boundary in this cell", not
  something flopy4 invented.
- **Field `shape` metadata doesn't change.** It already leaves out `nper`;
  only the declared type wraps it.
- **Precedents in develop:**
  - List packages store `dict[int, list[StressPeriodData]]` (`wel.py:111`).
  - TAS arrays are already a dict per header (Pass 3c, `structure.py:~985`).
  - `array_eq` already compares dicts key by key.
  - This brings array packages in line with all of these.

Affected fields, 24 in all, all in `gwf/` and `utl/spca` (gwt/gwe grid
packages aren't generated yet):

- `Optional[FloatArrayLike]` (15): `rivg.{stage,cond,rbot}`,
  `rcha.recharge`, `evta.{surface,rate,depth}`, `welg.q`,
  `drng.{elev,cond}`, `ghbg.{bhead,cond}`, `chdg.head`,
  `spca.{concentration,temperature}`
- `Optional[IntArrayLike]` with `index` (2): `rcha.irch`, `evta.ievt`
- `Optional[dict[str, FloatArrayLike]]` aux (7, becoming
  `dict[int, dict[str, FloatArrayLike]]`): `rivg`, `rcha`, `evta`,
  `welg`, `drng`, `ghbg`, `chdg`

## Input conversion

The examples pass dense `(nper, …)` arrays (twri `chd_head`, frenchman-flat
`q_crt`, circle `head`) and rely on "a period that's entirely DNODATA means
nothing new". For example, twri sets `chd_head` only in period 0 and expects
it to carry forward.

A converter on each field accepts:

- `dict[int, array]`: kept as given. This is the canonical form and the only
  way to write a clear explicitly.
- A dense `(nper, …)` array, split into periods. A period that's entirely
  `DNODATA` is dropped, which keeps today's meaning so the examples behave
  the same. Integer dense input keeps every period. Optionally, a period
  identical to the one before can be dropped; that's equivalent under
  carry-forward.

This mirrors how #398 kept DISV's array-style inputs working.

## Dense view

Plotting, xarray, adapters and NetCDF want `(nper, …)`. Add one method on
`Package`, e.g. `period_array(name, nper=None, carry_forward=True)`:

- **`carry_forward=True`:** each period holds the values in effect. Use this
  for plots and analysis. Grid packages need care: a period's arrays replace
  the previous period's as a whole, which a plain forward-fill per array does.
- **`carry_forward=False`:** missing periods get a fill value suited to the
  dtype (`FILL_DNODATA` for floats, `FILL_INT64` for ints). This is what
  NetCDF export needs; `netcdf.py:877` already uses `FILL_INT64` for
  integer encodings.

`nper` comes from the dims, the same as today's `_ArrayInfo`.

## Changes by file

**Codegen** (`utils/codegen/make.py` ~1314, ~1525)
- Wrap generated types for period arrays in `dict[int, …]`, and aux in
  `dict[int, dict[str, …]]`.
- Attach the converter.
- Regenerate the 9 packages.

**Package init** (`package.py`)
- Convert period arrays the same way `_init_dynamically_named_arrays`
  handles aux.
- Check the aux names as before, now per period.
- Grid packages: check that aux's periods are a subset of the stress
  fields' periods.

**Ingress, Pass 3b** (`structure.py:921-971`)
- Drop `_empty` and the pre-fill.
- Each parsed period sets `field[kper] = arr` in its native dtype.
- Integer fields parse as `int64`.
- An empty grid-package block sets the key to an all-`DNODATA` array for
  each stress field.
- This is also where PR #380's "unstored rows" (TAS references) go. See the
  open questions.

**Egress** (`unstructure.py:297-308`)
- Write one period block per key, across the union of keys from all the
  package's period fields.
- Remove the skip for periods that are entirely `FILL_DNODATA`.
- A grid-package period whose stress arrays are entirely `DNODATA` is
  written as an empty block.

**Index conversion** (`unstructure.py:149`, `_from_file_index`, `netcdf.py:273`)
- Plain ±1 on integer arrays, with no sentinel check.

**Writer filters** (`codec/writer/filters.py:197-205`)
- Recheck the hardcoded `FILL_DNODATA` mask. It should stay, but only for
  meaning 1.

**NetCDF** (`netcdf.py`)
- `_ArrayInfo` still declares a leading `nper`.
- Export builds data with `period_array(..., carry_forward=False)`.
- Import splits by the periods the ASCII file lists.

**Adapters, xarray** (`adapters.py:296`, `attrs_xarray.py:102`, `package.py:500`)
- Use the dense view.

**Constants**
- `FILL_DNODATA` is no longer needed to mark missing periods. It keeps only
  MF6's meaning.

**Tests**
- Update `test_rcha_irch_round_trip`: `irch` becomes an int dict with no
  3e30.
- Update the period-array tests in `test_mf6_codec.py`, `test_mf6_netcdf.py`
  and `test_mf6_integration.py`.
- New tests:
  - WELG round-trip with a cleared period
  - RCHA with `irch` given only in period 0
  - dense input converted with all-DNODATA periods dropped
  - the `period_array` views
- Run the docs examples, which use dense input.

## Effect on PR #380

- `reset_periods` goes away. A cleared period is a key whose stress arrays
  are entirely `DNODATA`.
- Storing integers as floats goes away, along with its cast.
- The rest of #380's period work has to be rebuilt on this model rather than
  merged.

## Decisions

1. **Dense input rule: accepted.** In dense `(nper, …)` input, a period
   that's entirely `DNODATA` means the period isn't given, so it carries
   forward. Document this on the converter. Clearing a period needs the dict
   form.
2. **Aux nesting: `aux[kper][name]`.** The period is the outer key for every
   period field, so aux fits the same pattern, and a grid period reads as
   one unit, as in MF6.
3. **Clear on write: empty block.** A grid-package period whose stress
   arrays are entirely `DNODATA` is written as `BEGIN PERIOD k` / `END
   PERIOD`.
4. **Key consistency: validate.** In grid packages, aux's periods must be a
   subset of the stress fields' periods. The check raises at init.

## Open, out of scope

- **TAS references** (`RECHARGE TIMEARRAYSERIES RchSeries`; the
  `test_tas_period_array_kept` xfail). A per-period value could later be an
  array or a TAS name. This representation can hold that; a dense array
  couldn't.

## Order

1. Converter and dense view on `Package`, with tests (no codegen change yet).
2. Codegen types and regeneration; Pass 3b; egress; index path.
3. NetCDF and adapters.
4. Examples and docs check; drop the `int-fill` item.
5. Then PR #380 rebases on top.
