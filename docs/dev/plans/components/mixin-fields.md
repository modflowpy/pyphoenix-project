# Mixins and MF6 versions

What mixins rely on in the generated classes, what breaks when a user syncs
to a different MF6 version, and how sync checks for it (#447, #449). A
reference note, to become a developer doc (see
[`dev-docs.md`](../maintenance/dev-docs.md)).

## Background

flopy4 generates a class per component (`Dis`, `Tdis`, `Gwf`, ...) from
MF6's definition files (DFNs), with one field per input setting.
`flopy4 mf6 sync` regenerates them for a chosen MF6 version, and versions
differ slightly in their fields.

The generated classes only hold data. Hand-written methods such as
`Dis.to_grid()` or a model's `output.head` live in mixins the generated
classes inherit from, and they read generated fields
(`DisMethods.to_grid()` reads `self.nlay`, `self.delr`, `self.crs`, ...).

## The problem

Mixins are written against the development version's fields. If a user
syncs to an older version lacking a field a mixin reads, the classes
generate fine, but calling the method fails with `AttributeError`. No
supported release (6.6.3, 6.7.0, 6.8.1) lacks anything the mixins use
today; it will matter once a mixin uses a new field.

## The check

Sync scans the mixins against the generated classes, in the subprocess
that already imports the staged modules before the swap. Gaps are
warnings: sync still generates, and only the methods named won't work.
Gaps are per method, so refusing to sync to an older MF6 over one
convenience method would be too strict. `flopy4 mf6 status` reports them
too.

- **What it scans** (`flopy4/mf6/_mixin_fields.py`): each mixin method's
  attribute chains from its class: `self.x`/`cls.x`; `self.parent.x` in a
  nested helper class; local names bound to a chain, including loop and
  comprehension variables (and `self.x or []`); `getattr(obj, "x")`; and
  keyword arguments to a class, including a local dict with literal keys
  passed as `cls(**kwargs)`.
- **How it resolves them:** by introspecting the attrs classes one step at
  a time. A field leads to the attrs classes its type can hold (child
  components, records, list items, through Optional and unions), an inner
  class to itself, and anything else present (a method, a property) ends
  the chain. An attribute that isn't there is a gap.
- **Per method, per class.** Each generated class using a mixin is
  checked, so a mixin shared by several models checks each model's own
  `oc`: `flopy4.mf6.gwf.dis.Dis: DisMethods.to_grid: no Dis.crs`.
- **`getattr` with a default** is a field the code does without, and isn't
  followed.

So mixin code should read fields in ways the scan sees. For example,
`TsMethods.from_series` passes `interpolation_method`,
`interpolation_methodrecord_single`, `sfac` and `sfacrecord_single` as
keyword arguments rather than building the names as strings.

`DimsProviderMethods` isn't in `MIXINS` and isn't scanned: codegen adds it
to every component that shares dimensions, and it loops over whatever
dimension fields the class has.

An earlier version (#447) had each mixin declare a `_requires` list,
checked at sync and kept honest by a test. The lists were only as good as
the scanner, so #449 dropped them and runs the scanner directly.

### Not caught

- Names built at run time, or `**kwargs` passed through from callers.
- Reads through things that aren't attributes or loops, e.g. indexing
  (`self.x[0].y`) or a function's return value.
- An unresolvable annotation, which ends the chain early, silently.

The backstop is the CI job that syncs to the latest MF6 release and runs
the tests against it, which catches what the scan misses as long as some
test calls the method. Widening it to every supported release would cover
them all.

## Why not type checking

Describing each mixin's needs as a `Protocol` for mypy doesn't do the same
job:

- mypy runs in our CI, for versions we test; the scan runs on the user's
  machine, for whatever version they sync to.
- mypy checks `self`-type annotations where methods are called, so a
  missing field is reported only if checked code calls the method.
- A Protocol repeats each field's exact type, which breaks for reasons
  unrelated to MF6 versions.

Protocols would still help type hints inside the mixins.
