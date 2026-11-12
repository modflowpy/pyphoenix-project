# flopy3's value API on period lists

**Status: not started, for later.** The current target is a clear path to migrate,
not unchanged 3.x scripts. Do this if that changes, or if `.get_data()` turns out
to be what real migrations trip on.

## Where things stand

flopy3's and flopy4's name are the same on most stress packages, and #541 made
flopy3's other period-list names work as attributes, by name only:

| flopy3 code | flopy4 today |
|---|---|
| `wel.stress_period_data` | the field, a `PeriodRows` |
| `lak.perioddata` | warns, returns `lak.stress_period_data` |
| `lak.perioddata = rows` | warns, assigns `lak.stress_period_data` |
| `wel.stress_period_data.get_data(0)` | `AttributeError`: `PeriodRows` has no `get_data` |
| `lak.perioddata.get_data(0)` | warns, then the same `AttributeError` |
| `sto.transient`, `oc.saverecord` | `AttributeError` pointing to `stress_period_data` |

So the `.get_data` rows are the gap. flopy3 scripts rarely stop at the name: its
`MFTransientList` has `.get_data(key=None, apply_mult=False)`,
`.set_data(data, key=None, autofill=False, replace=False)`, `.array` and `.data`.

## Proposal

`stress_period_data` is already a dict subclass. `flopy4.mf6.package.PeriodRows` holds its
package and coerces rows assigned to a period. So add flopy3's methods to it
instead of building a new type:

```python
class PeriodRows(dict):
    def get_data(self, key=None, apply_mult=False): ...
    def set_data(self, data, key=None, autofill=False, replace=False): ...

    @property
    def array(self): ...

    @property
    def data(self): ...
```

Each one warns with `DeprecationWarning` and names the flopy4 way to do the same
thing. Existing dict code keeps working, because the object is still the dict.

**Why not a subclass returned only by the legacy attribute?** There's no legacy
attribute where the name is the same: `wel.stress_period_data` is the field, so
flopy3's most common case wouldn't get the methods. It would also be a second
object, so `lak.perioddata[1] = rows` would change a copy, which brings back the
silent no-op #541 removed. Methods on the one object are simpler, and the cost is
only that scripts written for flopy4 can call them too, with a warning.

## What each one returns

`Flopy3ListData` in `flopy4/mf6/adapters.py` already builds flopy3's shapes for
plotting: a recarray per period (`.data`, `.array`), filled forward as in MF6. Reuse
it rather than writing a second flattener.

| Member | Behaviour | Source |
|---|---|---|
| `.data` | `{kper: recarray}` | `Flopy3ListData.data` |
| `.array` | recarray per period, `None` for none | `Flopy3ListData.array` |
| `.get_data(key)` | that period's recarray, filled forward | `Flopy3ListData._period` |
| `.get_data()` | every period, as `.data` | as above |
| `.set_data(data, key)` | `self[key] = data`, which coerces | `PeriodRows.__setitem__` |
| `.set_data(data)` | `data` a dict: each period | as above |

**Check against flopy3 first.** I confirmed the signatures, but the return shapes
above are from memory and the adapter's docstring. Compare them to a real
`MFTransientList` in the tests.

## Things to settle

- **Adapter construction.** `Flopy3ListData` takes a `Flopy3Package`, not a
  `Package`, and reads `pkg.to_dataframe()`. Either factor out the part that only
  needs the package, or build the adapter lazily. `adapters.py` imports from
  `package.py`, so the import has to stay inside the method either way.
- **Cost.** `Flopy3ListData.__init__` flattens every period up front, so calling
  `get_data(k)` in a loop over periods must not rebuild it each time. Caching needs
  invalidating on assignment, so a first version could just flatten one period.
- **Lossy cases.** The adapter gives `NaN` for a value that's a time series name,
  and `from_package` returns `None` for rows of more than one kind (a list of
  unions). Raise a clear error for the second, rather than returning `None`.
- **`apply_mult`, `autofill`, `replace`.** Accept the defaults, and raise for
  anything else unless real scripts need them.

## Out of scope

- **STO and OC.** Their old attributes keep raising. Reading them back needs an
  inverse of `sto_period_data` and `oc_period_data`, and assigning one needs to
  merge into the other's periods. That's separate work with separate edge cases.
- **Arrays** (`npf.k.array`, `dis.top.get_data()`). [`aliases-and-codemod.md`](aliases-and-codemod.md)
  leans against wrapping them, since numpy arrays can't take new methods. So this
  would leave period lists more compatible than arrays, and that's worth a
  deliberate decision before starting. [`replacing-flopy-mf6.md`](replacing-flopy-mf6.md) has
  the rule "same result or a clear error", which this proposal stretches: the name
  gives flopy4's dict, and only these members match flopy3.
- **The rest of `MFTransientList`** (`get_record`, `search_data`, `to_array`,
  `plot`, ...). Add what real scripts use, not the whole API.

## Tests

In `test/mf6/test_mf6_legacy.py`:

- Compare each member to a real `flopy.mf6.ModflowGwfwel` built from the same rows,
  including a period that fills forward and one given empty.
- `set_data` coerces rows, and `wel.stress_period_data` sees the change.
- Each member warns, and the warning points at the caller.

The migration tool's flag list in [`aliases-and-codemod.md`](aliases-and-codemod.md) (step 7) should drop
`.get_data` and `.set_data` for period lists once this lands.
