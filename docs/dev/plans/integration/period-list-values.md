# flopy3's value API on period lists

**Status: not started, for later.** The current target is a clear path to migrate,
not unchanged 3.x scripts. Do this if that changes, or if `.get_data()` turns out
to be what real migrations trip on.

## Where things stand

#541 made flopy3's period-list names work as attributes, by name only:

| flopy3 code | flopy4 today |
|---|---|
| `wel.stress_period_data` | warns, returns `wel.period_data` |
| `wel.stress_period_data = rows` | warns, assigns `wel.period_data` |
| `wel.stress_period_data.get_data(0)` | warns, then `AttributeError`: `PeriodRows` has no `get_data` |
| `sto.transient`, `oc.saverecord` | `AttributeError` pointing to `period_data` |

So the third row is the gap. flopy3 scripts rarely stop at the name: its
`MFTransientList` has `.get_data(key=None, apply_mult=False)`,
`.set_data(data, key=None, autofill=False, replace=False)`, `.array` and `.data`.

## Proposal

`period_data` is already a dict subclass. `flopy4.mf6.package.PeriodRows` holds its
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

**Why not a subclass returned only by the legacy attribute?** It looks tidier,
because `period_data` itself wouldn't carry flopy3's methods. But it would be a
second object, so `wel.stress_period_data[1] = rows` would change a copy, which
brings back the silent no-op #541 removed. A view that delegates
fixes that, at the cost of a whole mapping to maintain. Methods on the one object
are simpler, and the only cost is that `wel.period_data.get_data()` also works,
with a warning.

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
- `set_data` coerces rows, and `wel.period_data` sees the change.
- Each member warns, and the warning points at the caller.

The migration tool's flag list in [`aliases-and-codemod.md`](aliases-and-codemod.md) (step 7) should drop
`.get_data` and `.set_data` for period lists once this lands.
