# Migrating from flopy3

## Period data

flopy4 calls every package's period data `period_data`. flopy3 calls it
`stress_period_data` on some packages, and names others' after the input
file's variable. flopy4 still takes flopy3's names, but warns
(`DeprecationWarning`) and will stop taking them in a future release.

The old names also work as attributes, with the same warning, but only as
names. `wel.stress_period_data` is `wel.period_data`, a dict of rows by period,
not flopy3's `MFTransientList`, so `.get_data()` and `.set_data()` aren't there.
STO's and OC's old attributes raise `AttributeError`, since their values are
shaped differently: use `period_data`.

| flopy3 | flopy4 | packages |
|---|---|---|
| `stress_period_data` | `period_data` | CDB, CHD, CNC, CSUB, CTP, DRN, ESL, EVP, EVT, FLW, GHB, HFB, PCP, RCH, RIV, SRC, WEL, ZDG |
| `perioddata` | `period_data` | LAK, MAW, MVR, SFR, UZF, PRP, SPC, TVK, TVS |
| `lakeperioddata` | `period_data` | LKT, LKE |
| `reachperioddata` | `period_data` | SFT, SFE |
| `mwtperioddata`, `mweperioddata` | `period_data` | MWT, MWE |
| `uztperioddata`, `uzeperioddata` | `period_data` | UZT, UZE |
| `steady_state`, `transient` | `period_data` | STO |
| `saverecord`, `printrecord` | `period_data` | OC |

The values are the same, except for STO's and OC's.

The examples below also show differences the old names don't cover, which
you need to make anyway: flopy4's class names (`Sto`, not
`flopy.mf6.ModflowGwfsto`), and its constructors taking the parent as a
keyword (`parent=gwf`), not by position.

STO takes one entry per period, `STEADY-STATE` or `TRANSIENT`:

```python
# flopy3
sto = flopy.mf6.ModflowGwfsto(gwf, steady_state={0: True}, transient={1: True})

# flopy4
sto = Sto(parent=gwf, period_data={0: [("STEADY-STATE",)], 1: [("TRANSIENT",)]})
```

OC takes each period's saves and prints in one list, each starting with
`SAVE` or `PRINT`:

```python
# flopy3
oc = flopy.mf6.ModflowGwfoc(
    gwf,
    saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")],
    printrecord=[("BUDGET", "LAST")],
)

# flopy4
oc = Oc(
    parent=gwf,
    period_data={
        0: [("SAVE", "HEAD", "ALL"), ("SAVE", "BUDGET", "ALL"), ("PRINT", "BUDGET", "LAST")]
    },
)
```

As in flopy3, a list without periods is period 0's, and later periods
reuse it until another is given.
