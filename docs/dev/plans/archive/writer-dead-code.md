# Remove the writer's dead xarray-Dataset list path

Status: plan only (2026-10-23). This is follow-up cleanup to the converter
simplification (`simplify-converter`), and is best done once that branch
has merged. The single DFN-driven write path on that branch is what makes
this code dead.

## Why

The Jinja writer's `list` macro (`codec/writer/templates/macros.jinja`,
`{{ value|data2lines }}`) still handles values in the shapes egress
produced before Items existed:
- an `xr.Dataset` of period data, including OC as `save_*` / `print_*`
  data variables;
- a `DataArray`, including object dtype;
- a dict.

On the branch, egress (`converter/egress/unstructure.py`, `_Egress.field`
and `occurrences`) gives every list-typed value as a sequence: `Rows`, a
list of tuples, or a list of file-record tuples. Arrays go through the
`array` macro instead. So everything in the list path that isn't a
sequence is unreachable. That includes the stale `"perioddata"` branch
marked `# TODO: not working yet`.

## Evidence

The full `test/mf6` suite at `f46cfeca` (2395 passed, 6 skipped, 4
xfailed) was run with `data2list` and `dataset2list` wrapped:
- `data2list` was called 5,903 times, every time with a `Sequence`;
- `dataset2list` was never called.

Nothing calls either function directly, and no test does. The wrapper
was a pytest plugin, loaded with `-p probe_d2l`, `PYTHONPATH` set to its
directory, and `PROBE_OUT` set to an output directory. Write the counts
from `pytest_sessionfinish`, not `atexit`, so that xdist workers report:

```python
import collections, os
import flopy4.mf6.codec.writer.filters as F
hits = collections.Counter()
_d2l, _ds = F.data2list, F.dataset2list
def data2list(value):
    import xarray as xr
    from collections.abc import Sequence
    kind = ("seq" if isinstance(value, Sequence) else "dict" if isinstance(value, dict)
            else "dataset" if isinstance(value, xr.Dataset) else "dataarray")
    hits[kind] += 1
    return _d2l(value)
def dataset2list(value):
    hits["dataset2list"] += 1
    return _ds(value)
F.data2list, F.dataset2list = data2list, dataset2list
def pytest_sessionfinish(session):
    with open(os.path.join(os.environ["PROBE_OUT"], f"hits-{os.getpid()}.txt"), "w") as f:
        for k, v in hits.items():
            f.write(f"{k} {v}\n")
```

Re-run the probe after rebasing, before deleting anything, in case
develop has started handing the writer something new.

## The change

All of it is in `flopy4/mf6/codec/`. Line numbers are as of `f46cfeca`.

1. **Delete `dataset2list`** (`writer/filters.py`, ~345–436). This removes:
   - the `is_oc` special case and its `"perioddata"` TODO branch;
   - the aux-mask logic;
   - the per-row extraction loop.
2. **Remove the non-sequence branches of `data2list`** (~296–331): the
   dict branch, the Dataset branch and the DataArray branch. The dict
   branch is wrong as written anyway: `for name, val in value.values()`
   unpacks each value. What's left is `yield from value`. So delete
   `data2list` and have `data2lines` (~333) loop over `value` directly:

   ```python
   def data2lines(value: Sequence, inset: str = " ") -> str:
       """..."""
       return "\n".join(inset + " ".join(quote_if_needed(x) for x in row) for row in value)
   ```

   Keep `data2lines`' docstring about why it formats rows in Python
   rather than in a Jinja loop.
3. **Delete `nonempty`** (~281). Only the two functions above use it.
   Its `FILL_DNODATA` TODO goes with it.
4. **Drop the `data2list` filter registration**
   (`writer/__init__.py:25`). No template uses it.
5. **Narrow `field_type`** (`codec/filters.py`). Don't call an
   `xr.Dataset`, or a `DataArray` of object dtype, a list. With
   `dataset2list` gone, such a value would be written as its variable
   names. Raising `ValueError("Unsupported field type")` is better:
   - a `DataArray` is always `"array"`;
   - only a `Sequence` (list or `Rows`) is `"list"`.

   Keep the dict `"type"` branch. Whether it's still reachable hasn't
   been checked, so check it separately (the same probe idea works).
   Despite the module's name, only the writer uses this `field_type`. The
   reader's grammar codegen has its own (`reader/grammar/filters.py`).
6. **Imports.** Afterwards, `ruff check` will show what's unused in
   `writer/filters.py`: probably `Any`, perhaps `FILL_DNODATA` and some of
   `numpy`/`xarray`. Remove only what ruff flags. The array filters still
   use `np` and `xr`.

Expected size: about −130 lines, with no behaviour change.

## Tests

- `pixi run -e dev ruff check flopy4` and `ruff format --check`.
- All of `test/mf6`, with `mf6` on PATH for the integration tests. The
  written-file and load snapshots must not change. That is the check
  that nothing reached the deleted code.
  - Targeted subsets missed two broken test files during the
    `simplify-converter` rebase, so run the directory.
  - Integration tests need `mf6` on PATH. The pixi dev env has one at
    `.pixi/envs/dev/bin/mf6`.
- Add one small test: `field_type` raises on an `xr.Dataset`, so the
  narrowing in step 5 stays deliberate.

## Not in scope

- The `xr.Dataset` conversions in `flopy4/attrs_xarray.py` and
  `flopy4/mixins.py` (`to_xarray` / `from_dataset`). They're a separate
  API, not the writer's list path.
- `field_type`'s dict branch (see step 5).
