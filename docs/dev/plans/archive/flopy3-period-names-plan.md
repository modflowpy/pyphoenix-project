# Accept flopy3's period-data argument names

Status: plan only, deferred (2026-10-22). This is the flopy4 side of
`modflow-devtools/period-list-name-plan.md`. Do it before 4.0. The devtools
rename can land any time after, because it doesn't change flopy4's API.

## Why

flopy4 calls every package's period list `stress_period_data`, which is
documented and canonical. flopy3 names each argument after its v1 DFN
field, so many flopy3 scripts pass a name flopy4 rejects. flopy4 should
accept those names in 4.x with a deprecation warning, so that an upgraded
script still runs and says what to change. The STO and OC arguments also
need converting, because their values are shaped differently.

## The legacy names

**Plain renames.** The value is the same shape, so forward it unchanged to
`stress_period_data`:

| flopy3 argument | packages |
|---|---|
| `perioddata` | LAK, MAW, MVR, SFR, UZF, PRP, SPC, TVK, TVS |
| `lakeperioddata` | LKT, LKE |
| `reachperioddata` | SFT, SFE |
| `mwtperioddata`, `mweperioddata` | MWT, MWE |
| `uztperioddata`, `uzeperioddata` | UZT, UZE |

Derive the per-package list from the stored DFNs. It's the DFN name of the
fill-forward list, wherever that name isn't already `stress_period_data`.
Hard-code it only after the devtools rename, once the DFNs no longer carry
the old name.

Don't alias TDIS's `perioddata` or the grid packages' arrays. Those
already have the same names in flopy3 and flopy4.

**STO: `steady_state`, `transient`.** flopy3 takes one of these forms:
- `{kper: True}`, the common one;
- a bare `True`, meaning period 0;
- a list of periods.

Convert to `stress_period_data={kper: "steady-state" | "transient"}`. If
both are given, merge them. If they disagree on the same period, raise.

**OC: `saverecord`, `printrecord`.** flopy3 takes:
- a list of `(rtype, ocsetting...)` tuples, which applies to period 0 and
  fills forward. This is the common form, e.g. `saverecord=[("HEAD",
  "ALL")]`.
- a `{kper: [tuples]}` dict.

Convert each tuple to `("SAVE", rtype, *setting)` or
`("PRINT", rtype, *setting)`. Merge both arguments into one
`stress_period_data` list per period, saves first, which matches flopy3's
write order.

flopy3 also differs elsewhere, e.g. OC's `budget_filerecord` and
`head_filerecord` versus flopy4's `budget_file` and `head_file`. Those
belong in a wider flopy3-compat inventory, not here. Keep the same
mechanism, so they can be added later without redesigning anything.

## Mechanism

- **Metadata.** Each generated class gets a ClassVar, the same way it gets
  `headers`:

  ```python
  legacy_kwargs: ClassVar[dict[str, Legacy]] = {
      "perioddata": Legacy("stress_period_data"),
  }
  ```

  Here `Legacy(name, convert=None)` is a NamedTuple in `spec.py`, beside
  `Header`. `convert` names a function in a small hand-written module,
  `flopy4/mf6/legacy.py`, for the STO and OC reshapes. Codegen adds the
  entries:
  - plain renames, read from the DFN as described above;
  - STO and OC, from a short table in codegen.

- **Where the translation happens.** attrs generates `__init__` after the
  class body runs, so `__init_subclass__` can't wrap it, and attrs'
  `alias=` allows only one name. Translate in a `__call__` on a metaclass
  for `Component`, derived from `ABCMeta`, because `Component` is already
  an ABC. Before calling `__init__`, for each key in `legacy_kwargs`:
  - pop it;
  - convert it;
  - emit `DeprecationWarning(f"{cls.__name__}({old}=...) is deprecated;
    use {new}=...")` with `stacklevel` pointing at the user's line;
  - pass it on under the new name.

  If both the old and the new name are given, raise `TypeError`.

  If a metaclass looks too heavy, the fallback is to have the template emit
  an explicit `__init__` wrapper for classes with legacy names, using
  `attrs.define(init=False)` and calling `__attrs_init__`. That's more
  generated code, but the mechanism is local to the class.

- **Scope.** Only constructor keywords. Don't add attribute aliases such as
  `lak.perioddata`: flopy3 code that reads these attributes back is rare,
  and properties would clutter the classes. Mention this in the migration
  guide.

## Tests

- Each plain alias builds an object equal to one built with the
  `stress_period_data` form, and warns once.
- STO: `{0: True}`, `True` and the list form all convert. Conflicting
  `steady_state` and `transient` raise.
- OC: the list form and the dict form convert, and save/print merge in
  order.
- Passing both the old and the new name raises `TypeError`.
- A class without legacy names gets no metaclass overhead beyond an
  empty-dict check.
- After the devtools rename, regenerate and check that `legacy_kwargs`
  doesn't change.

## Docs

The migration guide gets a section with the old-name/new-name table, and
before/after examples for STO and OC. Keep the docs examples on the new
names. Use the aliases only in the guide.

## Removal

The plain renames are cheap, so keep them through 4.x. Consider dropping
the STO and OC converters at 5.0. Escalate the warning to
`FutureWarning`, which users see by default, one minor release before
removal.
