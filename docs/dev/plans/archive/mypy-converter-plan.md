# Let mypy see field converters

Status: abandoned. The work was done on branch `mypy-converters` (2026-10-08)
but never merged, and #433 is closed. Record fields used a lambda converter
(`attrs.Converter` isn't readable by mypy), so they accepted any value
statically. By 2026-11-04 the plugin was a no-op on develop, because the field
functions (#463) replaced the `field()` and `path()` it hooks. Installed
packages also got nothing from it, because flopy4 has no `py.typed`. See
[`constructor-stubs.md`](../components/constructor-stubs.md) for the plan that
replaces it.

## Problem

Generated fields are declared with flopy4's `field()`/`path()` wrappers
(`flopy4/mf6/spec.py`). mypy's attrs plugin recognizes only `attrs.field`,
`attr.ib` and similar, so it ignores the wrappers' `converter=`. Every
`__init__` argument therefore takes only the annotated type, even where
the converter accepts more:

- `Oc(budget_file="x.cbc")` is rejected (`Path | None` expected), though
  `attrs.converters.optional(Path)` accepts it.
- `Gwf(newtonoptions=True)` is rejected, though `Record.from_flag` accepts
  it.

Widening the annotations would make reads like
`gwf.newtonoptions.under_relaxation` type errors, so that's out.

## Approach: an opt-in mypy plugin

Ship `flopy4/mypy_plugin.py`. It adds the wrappers to the attrs plugin's
field-function set:

```python
import mypy.plugins.attrs as attrs_plugin
from mypy.plugin import Plugin

attrs_plugin.attr_attrib_makers.update({"flopy4.mf6.spec.field", "flopy4.mf6.spec.path"})


def plugin(version):
    return Plugin
```

Tried on mypy 2.3.1 in a scratch config:

- `Gwf(newtonoptions=True)`, `Npf(xt3doptions=True)` and
  `Oc(budget_file="x.cbc")` pass.
- Attribute types are unchanged.

## Steps

1. **Add the plugin**, and enable it in `[tool.mypy]`
   (`plugins = ["flopy4.mypy_plugin"]`).
2. **Make converters readable.** mypy only reads a converter that's a
   named function, a type or a lambda. The plugin reports 32 that aren't:
   - 27 are `attrs.converters.optional(to_array(np.str_))`. Generate a
     named module-level converter in `_types.py` (e.g.
     `to_optional_str_array`) and use it from `filters.field_converter`.
   - 5 are `X.from_flag` on nested record classes. Options:
     - a module-level `record_flag(value: Record | bool | None)` typed
       for mypy, which looks the record class up from the field at
       conversion time (an `attrs.Converter` with `takes_field=True`);
     - a lambda, `lambda v: Gwf.Newtonoptions.from_flag(v)`;
     - a generated `# type: ignore[misc]`.

     Prefer the first if `attrs.Converter` gives mypy a readable
     argument type; check it.
   - Then `mypy flopy4` is clean with the plugin on.
3. **Leave `child()` out.** Its default lives in the wrapper's signature,
   and the plugin only reads arguments written in the call, so every
   child would look required. Children don't need it.
4. **Tests:** a mypy test (`mypy.api.run` on a snippet, marked slow if
   needed). It checks that:
   - the bool, str and record forms are accepted;
   - a wrong type is still rejected;
   - reading the attribute keeps the record type.
5. **Docs:** a line in the user docs on adding the plugin to a mypy
   config.

## Caveats

- `attr_attrib_makers` is a mypy internal (`Final`), not a public hook. A
  mypy release could break it. Pin a tested range, or have the test catch
  a break.
- Users only benefit if they enable the plugin. Without it, they get
  today's behavior.
- Pyright/Pylance gets nothing. It has no plugins and doesn't read
  converters.

## Alternative, not planned

Codegen could emit a typed `__init__` under `if TYPE_CHECKING:` in every
class. It has to list every constructor argument, including the hand-written
bases' (`name`, `workspace`, `parent`, `dims`, …), and keep them in sync.

Correction (2026-11-04): this said the approach works for mypy and Pyright,
but it only works for Pyright. mypy's attrs plugin ignores that `__init__` and
uses the generated one. Generated `.pyi` stubs work for both: see
[`constructor-stubs.md`](../components/constructor-stubs.md).
