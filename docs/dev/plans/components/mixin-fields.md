# Mixins and MF6 versions: what can break, and how we guard against it

**Status (2026-10-19):** reference doc. `mixin-field-paths` merged as #449
("better mixin field checking"), after #447. To be rewritten for
`docs/dev/` (see [`dev-docs.md`](../maintenance/dev-docs.md)).

Written 2026-10-09, updated after #442 (dims from schema), and again
2026-10-10 for `mixin-field-paths`, which replaces the declarations with
a check of the generated classes (see "The replacement").

## Background, in brief

**flopy4 builds its classes from MF6's definition files.** MODFLOW 6 (MF6)
ships definition files ("DFNs") describing every input: each package, and
each setting in it. For example, the structured grid package `gwf-dis` has
settings like `nlay` (number of layers), `delr` (column widths) and `crs`
(coordinate reference system). flopy4 reads the DFNs and *generates* a
Python class per package (`Dis`, `Tdis`, `Gwf`, ...) with one attribute per
setting. We call those settings **fields**.

**Users can regenerate for their MF6 version.** `flopy4 mf6 sync`
regenerates the classes from a chosen MF6 version's DFNs, e.g. the latest
release (6.8.1) instead of the development version. Different versions
have slightly different fields: newer versions add some.

**Mixins add handwritten methods.** The generated classes only hold data.
Convenience methods, like `Dis.to_grid()` (turn the grid settings into a
grid object) or the model's `output.head` (read simulated heads), are
written by hand in small classes called **mixins**, which the generated
classes inherit from. A mixin's code reads the generated fields, e.g.
`DisMethods.to_grid()` reads `self.nlay`, `self.delr`, `self.crs`, ...

## The problem

The mixins are written against the development version's fields. If a
user syncs to an older MF6 version that lacks a field a mixin reads, the
classes generate fine, but calling that method fails at run time with an
`AttributeError`. Nothing warns them beforehand.

None of the supported releases (6.6.3, 6.7.0, 6.8.1) lack anything the
mixins use today, so this hasn't bitten anyone. But it will as soon as a
mixin starts using a new field.

## What `mixin-requires` adds

1. **Each mixin declares the fields it needs**, in a `_requires` list:

   ```python
   class DisMethods:
       _requires: ClassVar[frozenset[str]] = frozenset({"nlay", "delr", "crs", ...})
   ```

2. **Sync checks the list before writing anything.** If the DFNs being
   synced lack a declared field, sync stops with a clear message, e.g.
   `DisMethods on gwf-dis: crs`, instead of producing classes that fail
   later.

   (The check reads `_requires` from the source file instead of importing
   the mixin, because importing it can import generated classes, and sync
   has to work even when those are broken.)

3. **A test keeps the lists honest.** It reads each mixin's code, finds
   every `self.<name>` where `<name>` is one of its package's DFN fields,
   and fails if that name isn't in `_requires`. So if someone uses a DFN
   field in a mixin without listing it, the test fails.

## The gaps, and the replacement (`mixin-field-paths`)

As first merged, the test only recognized one way of reading a field:
**directly on `self`, under the exact DFN name, on the package the mixin
belongs to.** The mixins already read fields other ways, all undeclared
and unchecked: through another object (`self.parent.oc.head_file`),
under Python names that differ from DFN names (`time_series_name`,
`tdis`), by string (`getattr`), and as record members and inner classes
(`cls.Timeseries(ts_time=...)`).

`mixin-field-gaps` (not merged) extended the declarations and the test to
cover most of these. But the lists were only as good as the scanner
keeping them honest, so `mixin-field-paths` drops the lists and runs the
scanner at sync time, against the generated classes themselves:

- **Where:** in the subprocess that already imports the staged modules
  before the swap (`sync-import-check`). Gaps are warnings: sync still
  generates, and only the methods named won't work. `flopy4 mf6 status`
  reports them too.
- **What it scans** (`flopy4/mf6/_mixin_fields.py`): each mixin method's
  attribute chains from its class: `self.x`/`cls.x`; `self.parent.x` in a
  nested helper class; local names bound to a chain, including loop and
  comprehension variables (and `self.x or []`); `getattr(obj, "x")`; and
  keyword arguments to a class, including a local dict with literal keys
  passed as `cls(**kwargs)`.
- **How it resolves them:** by introspecting the real attrs classes, one
  step at a time: a field leads to the attrs classes its type can hold
  (child components, records, list items, through Optional and unions),
  an inner class to itself, and anything else present (a method, a
  property) ends the chain. An attribute that isn't there is a gap.
- **Per method, per class.** Each generated class using a mixin is
  checked, so a mixin shared by several models checks each model's own
  `oc`, and messages name the method:
  `flopy4.mf6.gwf.dis.Dis: DisMethods.to_grid: no Dis.crs`.
- **`getattr` with a default** is a field the code does without, and
  isn't followed.

`TsMethods.from_series` used to build two attribute names as strings.
It now passes all four (`interpolation_method`,
`interpolation_methodrecord_single`, `sfac`, `sfacrecord_single`) as
keyword arguments, so the scan sees them.

### Still not caught

- names built at run time, or `**kwargs` passed through from callers
- reads through things that aren't attributes or loops, e.g. indexing
  (`self.x[0].y`) or a function's return value
- an unresolvable annotation ends the chain early (silently)

The backstop is still the CI job that syncs to the latest MF6 release
and runs the tests against it. That catches what the scan misses, as
long as some test calls the method. Widening it to every supported
release (6.6.3, 6.7.0, 6.8.1) would cover them all.

(`DimsProviderMethods` isn't in `MIXINS` and isn't scanned: codegen adds
it to every component that shares dimensions, and it loops over whatever
dimension fields the class has.)

### Warn, don't fail

Gaps are per method, so sync warns and generates anyway, rather than
refusing to sync to an older MF6 over one convenience method.

## Why not type checking instead?

We considered describing each mixin's needs as a typing `Protocol` and
letting mypy check them. We passed on it because:

- mypy only runs in our CI, for versions we test. The declared list is
  checked on the user's machine, for whatever version they sync to.
- mypy checks this kind of `self` annotation where methods are called,
  so a missing field is only reported if some checked code calls that
  method.
- A Protocol has to repeat each field's exact type, which breaks for
  reasons unrelated to MF6 versions.

Protocols would still be nice for type hints inside the mixins, and the
required names could later be read from them.
