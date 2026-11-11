# `Simulation.load` fails on an OC print format with no format word

Found by the DDL slice's corpus run, 2026-11-05, at flopy4 `8d25e4b7`. Not fixed.

`mf6/test/test060_gms_ets` is the one model in `mf6/test` that doesn't load, and
MF6 runs it to normal termination (`bin/mf6`, `1469b358b9`).

```
TypeError: Oc.Format.__init__() missing 1 required positional argument: 'format_'
```

The line it fails on, in `ets3_dis.oc`'s OPTIONS block:

```
HEAD PRINT_FORMAT COLUMNS 10 WIDTH 11 DIGITS 4
```

## Cause

`format_` is required (`flopy4/mf6/gwf/oc.py:27`), but MF6 doesn't require the word.
flopy4 is following the spec here, and the spec is stricter than MF6:

- The DFN says `optional false` for `format`, in the OC `formatrecord`.
- MF6's `print_format` (`src/Utilities/InputOutput.f90`, the loop after line 1475)
  walks whatever words remain after `DIGITS`, and exits cleanly when there are none.
  The caller's edit descriptor stands.

So this is a gap between the DFN and MF6 rather than a parsing mistake. A fix in
flopy4 alone would diverge from the DFN.

## To decide when fixing

- Make `format_` optional in `Oc.Format`, and check that it writes back without the
  word rather than as `None`.
- Whether the DFN should also say `optional true`. That's a change in MF6, and then
  a new devtools snapshot.
- `grep -rn 'format_: str' flopy4/mf6` for the other components with the same record.
- `columns` and `width` are the reverse: optional in `Oc.Format`, but MF6 requires
  them (the `nwords >= 4` check in the same routine).

## After fixing

The model isn't in `KNOWN_PASSING` (`test/mf6/test_mf6_load_all_models.py`), so it's
an xfail today, and should be added. Reproduce with:

```python
workspace = copy_to(tmp_path, "mf6/test/test060_gms_ets", verbose=False)
Simulation.load(workspace / "mfsim.nam")
```
