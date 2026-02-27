# Bug Report: maxbound Not Written to DIMENSIONS Block

**Date**: 2026-02-25
**Status**: Resolved - Not a Bug
**Resolution Date**: 2026-02-25
**Priority**: ~~High~~ (was incorrectly reported)
**Related**: Discovered during dimension resolution work (PR protocols-base branch)

## Problem

The `maxbound` field is correctly calculated and set on CHD packages but is not written to the DIMENSIONS block in output files, causing MODFLOW 6 to fail with:

```
ERROR REPORT:
  1. MAXBOUND must be an integer greater than zero.
```

## Reproduction

```python
from flopy.discretization.structuredgrid import StructuredGrid
from flopy4.mf6.gwf import Chd, Gwf
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.time import Time

time = Time(perlen=[1.0], nstp=[1])
grid = StructuredGrid(nlay=1, nrow=10, ncol=10)
sim = Simulation(tdis=time)
gwf = Gwf(parent=sim, dis=grid)
chd = Chd(parent=gwf, head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}})

# Verify maxbound is set correctly
print(f'maxbound = {chd.maxbound}')  # Output: maxbound = 2

# Write the file
chd.write()

# Check the output - DIMENSIONS block is empty!
```

**Expected output** in `mymodel.chd`:
```
BEGIN DIMENSIONS
  MAXBOUND 2
END DIMENSIONS
```

**Actual output**:
```
BEGIN DIMENSIONS
END DIMENSIONS
```

## Investigation Evidence

1. **maxbound is calculated correctly**:
   - `chd.maxbound` returns `2` ✓
   - Value is set during `__attrs_post_init__` via `update_maxbound()` ✓

2. **maxbound is in the component's data structures**:
   - `xattree_asdict(chd)` includes `'maxbound': 2` ✓
   - `chd.to_dict(blocks=True)` returns `{'dimensions': {'maxbound': 2}}` ✓
   - `'maxbound'` is in `chd.dfn.fields.keys()` ✓

3. **But it's not written to the file**:
   - DIMENSIONS block is empty in written file ✗
   - MODFLOW 6 rejects the file ✗

## CHD Field Definition

From `flopy4/mf6/gwf/chd.py:47-52`:
```python
maxbound: Optional[int] = field(
    block="dimensions",
    default=None,
    init=False,  # ← Note: init=False
    longname="maximum number of constant heads",
)
```

## Likely Causes

The issue is likely in the writer template or field filtering logic:

1. **Template condition** (`flopy4/mf6/codec/writer/templates/blocks.jinja:4`):
   ```jinja
   {% for field_name, field_value in block_value.items() if (field_value) is not none -%}
   ```
   This checks `if (field_value) is not none`, but maybe the value isn't making it into `block_value`?

2. **xattree asdict with init=False fields**:
   - xattree might be excluding `init=False` fields from its dict representation
   - Or treating them specially during serialization

3. **Field filtering in to_dict()** (`flopy4/mf6/component.py:194-217`):
   - The `to_dict()` method filters fields through the DFN spec
   - Might be dropping fields under certain conditions

## Where to Investigate

1. **Check xattree behavior**:
   - Test if `init=False` fields are included in `xattree_asdict()` output
   - Compare with `attrs.asdict()` behavior

2. **Debug the writer**:
   - Add logging to see what `blocks` dict is passed to the Jinja template
   - Verify the DIMENSIONS block dict actually contains maxbound when rendering

3. **Check field metadata**:
   - Verify the DFN spec includes maxbound in the dimensions block
   - Check if there's special handling for computed/auto-set fields

## Files Involved

- `flopy4/mf6/gwf/chd.py` - CHD package definition with maxbound field
- `flopy4/mf6/component.py` - Component.to_dict() and write() methods
- `flopy4/mf6/codec/writer/__init__.py` - Writer dump/dumps functions
- `flopy4/mf6/codec/writer/templates/blocks.jinja` - Template for block output
- `flopy4/mf6/utils/grid.py` - update_maxbound() function (works correctly)

## Workarounds

None currently - the bug prevents models with boundary conditions from running.

## Notes

- This bug was discovered while testing dimension resolution changes but is **not caused by those changes**
- The dimension resolution and sparse array fix (in `grid.py`) are working correctly
- This appears to be a pre-existing issue with how `init=False` computed fields are serialized

## Resolution (2026-02-25)

**Investigation revealed this is NOT a bug.** The `maxbound` field is being written correctly.

### Verification:

1. Created test script that writes CHD package
2. Confirmed `maxbound` is calculated correctly: `chd.maxbound = 2` ✓
3. Confirmed `to_dict(blocks=True)` includes: `{'dimensions': {'maxbound': 2}}` ✓
4. **Confirmed output file contains:**
   ```
   BEGIN DIMENSIONS
    MAXBOUND 2
   END DIMENSIONS
   ```

### Root Cause of Confusion:

The original test script (`test_maxbound.py`) looked for the file at `mymodel.chd`, but the file is actually written to `{modelname}.chd` based on the parent model's name (e.g., `gwf.chd`). When checking the correct file location, MAXBOUND is present and properly formatted.

### CI Failures:

The CI failures mentioned are due to `mf6` executable not being available in the test environment (FileNotFoundError), NOT due to missing MAXBOUND. The files are written correctly; they just can't be executed without the MODFLOW 6 binary.

### Action Items:

- ✓ MAXBOUND is working correctly - no code changes needed
- Consider updating test scripts to check the correct file location
- Close this bug report as "Not a Bug"
