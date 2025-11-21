# Typed Grammar Issues

This document catalogs issues with generated typed grammars that cause fallback to the basic parser.

## Overview

The typed parser uses auto-generated Lark grammars for each MF6 component type (e.g., `gwf-nam.lark`, `gwf-chd.lark`, `gwf-disv.lark`). When these grammars have errors or are incomplete, parsing falls back to the basic (untyped) parser.

The basic parser returns blocks as flat lists of lines, requiring the mapper layer to use heuristic workarounds. The typed parser with `__default__()` returns properly structured dicts, eliminating the need for workarounds.

## Issue 1: Rule Name Conflicts

**Component**: GWF (model-level name file)
**File**: `flopy4/mf6/codec/reader/grammar/generated/gwf-nam.lark`
**Error**: `Rule 'list' defined more than once`

### Root Cause

The grammar imports a `list` rule from the typed module (for structured list/recarray data), then tries to define its own `list` rule for the LIST filename option:

```lark
%import typed.list -> list        # Line 10: imports 'list' rule
...
list: "list"i string              # Line 29: field rule for LIST option
```

Lark doesn't allow duplicate rule names, so the grammar fails to compile.

### Why This Happens

The grammar generator creates a rule for each field using the field's name. When a field name conflicts with an imported rule name (`list`, `record`, `array`, etc.), we get a collision.

### Fix Options

**Option A**: Grammar generator should detect conflicts and rename field rules
```lark
list_option: "list"i string       # Renamed to avoid conflict
```

**Option B**: Grammar generator should use a consistent prefix for field rules
```lark
field_list: "list"i string
field_newton: "newton"i "under_relaxation"i
```

**Option C**: Don't import unused rules (if `list` structured data isn't used in this file)

### Impact

- GWF model-level files always fall back to basic parser
- Affects every simulation (all have GWF name files)
- Lower priority since name files are simple (just file listings)

### Workaround

The basic parser handles name files fine, just less cleanly. Not urgent.

---

## Issue 2: Missing Keywords in Grammar

**Component**: NPF (Node Property Flow package)
**File**: `flopy4/mf6/codec/reader/grammar/generated/gwf-npf.lark`
**Error**: `Unexpected token Token('__ANON_2', 'wetfct') at line 3, column 10`

### Root Cause

The NPF file contains a `wetfct` keyword that's not defined in the generated grammar. This suggests:
1. The grammar generator missed a field from the definition file
2. The definition file is incomplete
3. The keyword is deprecated or from a different MF6 version

### Example File Content

```
BEGIN options
  SAVE_FLOWS
  wetfct 0.1
  ...
END options
```

The grammar likely has:
```lark
options_fields: (save_flows | ... )*
# Missing: wetfct rule
```

### Fix

Check the NPF definition file (DFN) and ensure all valid options are included in the grammar generation process. Add:
```lark
wetfct: "wetfct"i double
```

### Impact

- NPF files with `wetfct` option fall back to basic parser
- Affects models using wetting/drying functionality
- Medium priority (common in certain model types)

---

## Issue 3: Strict Whitespace Handling

**Component**: DISV (Vertex discretization)
**File**: `flopy4/mf6/codec/reader/grammar/generated/gwf-disv.lark`
**Error**: `Unexpected token Token('NEWLINE', '\n') at line 8, column 10. Expected one of: END, NVERT, NCPL, NLAY`

### Root Cause

The grammar expects dimension fields to appear consecutively without extra whitespace:

```lark
dimensions_fields: (nlay | ncpl | nvert)*
```

But MF6 files often have blank lines or extra spacing:
```
BEGIN dimensions
  NLAY  1
  NCPL  121
                    # <-- This blank line causes the error
  NVERT  148
END dimensions
```

### Why This Happens

The grammar correctly ignores whitespace within lines (`%ignore WS`) and comments (`%ignore SH_COMMENT`), but doesn't handle optional newlines between field definitions gracefully.

The `*` operator means "zero or more fields", but the parser gets confused when it sees a NEWLINE after fields but before END.

### Fix Options

**Option A**: Make the grammar more permissive about newlines
```lark
dimensions_fields: (NEWLINE* (nlay | ncpl | nvert) NEWLINE*)*
```

**Option B**: Add explicit newline handling in the grammar
```lark
dimensions_fields: (dimension_field)*
dimension_field: (nlay | ncpl | nvert) NEWLINE+
```

**Option C**: Preprocess files to remove blank lines (not recommended)

### Impact

- DISV models always fall back to basic parser
- Affects all vertex discretization models
- **High priority** - common model type

### Workaround

The basic parser handles DISV files, but loses the clean dict structure benefits. The mapper workarounds compensate.

---

## Issue 4: OC Print Format Keywords

**Component**: OC (Output Control)
**File**: `flopy4/mf6/codec/reader/grammar/generated/gwf-oc.lark`
**Error**: `Unexpected token Token('__ANON_2', 'COLUMNS') at line 5, column 23`

### Root Cause

The OC file has print format keywords that aren't in the grammar:

```
BEGIN options
  HEAD PRINT_FORMAT COLUMNS 10 WIDTH 15 DIGITS 6 GENERAL
  ...
END options
```

The grammar likely only has:
```lark
head: "head"i "fileout"i word
```

But not:
```lark
head_format: "head"i "print_format"i "columns"i integer "width"i integer ...
```

### Fix

The grammar needs to handle both HEAD FILEOUT and HEAD PRINT_FORMAT variants:
```lark
head: head_fileout | head_format
head_fileout: "head"i "fileout"i word
head_format: "head"i "print_format"i format_spec
format_spec: ("columns"i integer)? ("width"i integer)? ...
```

### Impact

- OC files with print format options fall back to basic parser
- Common in models with detailed output control
- Medium priority

---

## Statistics

### Fallback Frequency

To measure fallback frequency, search for warnings in test output:
```python
grep "Typed parsing failed for" test_output.txt | sort | uniq -c
```

Expected common failures:
- **Gwf**: Every simulation (name file has `list` conflict)
- **Disv**: Most vertex grid models (whitespace issue)
- **Npf**: Some models (missing keywords)
- **Oc**: Some models (format keywords)

### Success Rate

Components with **working** typed grammars:
- CHD (Constant Head)
- DRN (Drain)
- WEL (Well)
- RIV (River)
- GHB (General Head Boundary)
- RCH (Recharge)
- Most other boundary packages

These benefit from the `__default__()` structured output immediately.

---

## TODO

1. Fix high-priority grammar issues:
   - DISV whitespace handling (affects many models)
   - Rule name conflicts in GWF/GWT/GWE name files
2. Validate generated grammars: add CI check that all grammars compile
3. Document known limitations: which keywords/options aren't supported
4. Consider whether basic parser can structure blocks as dicts too?

## Testing Strategy

### Verify Typed Parsing Works

```python
from flopy4.mf6.codec.reader import loads
from flopy4.mf6.gwf.chd import Chd

# Should NOT see fallback warning
data = loads(chd_file_content, component_type=Chd)
assert isinstance(data['dimensions'], dict)  # Clean structure
```

### Verify Fallback Still Works

```python
# Even if typed parsing fails, basic parser should work
data = loads(disv_file_content, component_type=Disv)
# Will see fallback warning, but still get data
assert 'dimensions' in data
```
