# Typed constructors through generated stubs

Status: not started and not scheduled. Worth doing before flopy4 ships
`py.typed`, or once editor errors on valid code start to matter.

Checked against develop `8d25e4b7` on 2026-11-04, with mypy 2.3.1 and
Pyright 1.1.414. The stub design was tried by hand on `Npf`, for a few of
its 29 arguments. Generating stubs is untested.

## Problem

A generated field's converter accepts more than its annotation says.
`Npf(rewet=(1.0, 1, 0))` and `Oc(budget_file="x.cbc")` work at runtime, but
their annotations are `Rewet | None` and `Path | None`. Widening the
annotations is out, because reads like `npf.rewet.wetfct` would stop
type-checking. A field needs one type for reads and a wider one for
arguments.

What type checkers do today:

| Checker and setup | What happens |
|---|---|
| mypy, source on the path | Rejects valid plain values, and rejects garbage |
| mypy, installed package | Treats flopy4 as `Any`, because there's no `py.typed` |
| Pyright/Pylance | Treats `Component` constructor calls as unchecked, and `Npf()` as `Any` |

The Pyright row is `LegacyKwargs.__call__` (`flopy4/mf6/legacy.py`, #503).
It's typed `-> Any`, and Pyright uses a metaclass `__call__` in place of
`__init__`.

## Approach

Generate a `.pyi` next to each generated module, using the same specs as
the module. The stub stays an attrs class, with `init=False` and an explicit
`__init__`:

```python
@attrs.define(kw_only=True, slots=False, init=False)
class Npf(Package):
    @attrs.define
    class Rewet(Record):
        wetfct: float
        iwetit: int | None = None
        ihdwet: int | None = None

    rewet: Rewet | None  # reads keep the narrow type

    def __init__(
        self,
        *,
        name: str | None = None,
        rewet: Rewet | tuple[float, int, int] | None = None,
        ...
    ) -> None: ...
```

With the metaclass `__call__` hidden from checkers, this prototype gave the
same results in mypy and Pyright:

- Valid plain values pass, and garbage is rejected.
- `npf.rewet` reads as `Rewet | None`.
- `Npf.Rewet(...)` gets a typed constructor.

Under mypy, `attrs.fields(Npf)`, `attrs.evolve(...)` and `mypy flopy4` also
pass. The `Rewet` fields above are illustrative: confirm them against the
generated class.

### Alternatives

| Alternative | Why not |
|---|---|
| `__init__` under `if TYPE_CHECKING:` in the `.py`, as `mypy-converter-plan.md` suggested | mypy's attrs plugin ignores it and uses the generated `__init__`. Only Pyright honors it |
| mypy plugin (draft #433) | mypy only, relies on a mypy internal, and its lambda converters accept any value. It also hooks the removed `field()`/`path()` |
| Stub with a plain class | Handles constructors, but the class stops being an attrs class to checkers, for no gain |

## What each argument accepts

This table is what the generator has to encode, and it's the bulk of the
work. Counts are own constructor arguments across 129 generated classes,
1427 in all. "Known" comes from reading the code. Everything else needs the
survey in step 2.

| Kind | Count | Argument type | Status |
|---|---|---|---|
| `keyword` | 436 | `bool` | Known |
| `array` | 207 | Annotation plus constants, layers and xarray; `Npf(k=1.0)` runs but mypy rejects it. Period arrays are keyed by period and may hold `None` or a series name. Inline string arrays take `str \| Iterable[str]` | Survey the numeric and period forms |
| `child` | 202 | Annotation, plus what each candidate's `coerce` accepts; a list field also takes a single value | Survey `coerce` |
| `list` | 121 | Rows, in the forms `_coerce_rows` and the item classes accept | Survey; likely a shared alias |
| `file` | 113 | `str \| PathLike`, plus `None` if optional | Known |
| `string` | 110 | Annotation | Check time-series and `empty_is_none` |
| `integer` | 103 | Annotation | Check numpy integers |
| `double` | 94 | What `to_double` accepts | Survey |
| `record` | 23 | See below | Rules known, generation untested |
| reference | 18 | Annotation, already `Model \| str` | Known |

### Records

Few fields, but the forms depend on the record's own fields. The rules
follow `Record.convert`:

- **Always:** the record class, `None` and `Mapping[str, Any]`.
- **`bool`:** only if the record has a keyword and no required fields.
- **`tuple`:** the field types in order, with one shape per arity when
  trailing fields are optional.
- **First value alone:** the first field's type, if the rest are optional.
- **One nested record:** that record, plus its forms.
- **One array field:** one element, or an iterable of them.
- **`str`:** see the open questions. Every record accepts one at runtime.

`lists/record-unify.md` would change `Record`, so check it first.

## Steps

1. **Stop `LegacyKwargs.__call__` hiding constructors.** Put it behind
   `if not TYPE_CHECKING:`. Also check `_LegacyInputs` in `disv_methods.py`,
   which the prototype didn't cover. This restores Pyright's types and
   brings back false errors on plain values, until stubs land. It can ship
   alone: see the open questions.
2. **Survey accepted values.** Fill in the table above, with a parametrized
   runtime test per kind. These tests keep the stubs from promising a form
   the runtime rejects.
3. **Generate the stubs.**
   - Add `package.pyi.jinja`, and write the stub from `make_module`, using
     the existing `ComponentSpec`.
   - Add `filters.init_type`, next to `filters.py_type` and `converter`.
   - A stub replaces its whole module for checkers, so it has to cover
     everything public: bases and mixins, nested record, item and block
     classes, `ClassVar`s, properties and module-level names.
   - Read inherited arguments (`name`, `filename`, `dims`, `workspace`, ...)
     from the bases' `attrs.fields` rather than hardcoding them, using
     their aliases.
   - Have `make_package_inits` write `__init__.pyi` with explicit
     re-exports (`from x import X as X`).
4. **Include stubs in sync and packaging.**
   - Add the stubs to the file list in `_contract.py`, so that `flopy4 mf6
     sync` stages, swaps and rolls them back with their modules.
   - Add `**/*.pyi` to `[tool.setuptools.package-data]`.
   - `components/user-dir-classes.md` would need to carry stubs too.
5. **Test for drift.** For each generated class:
   - Parse the stub, and compare its `__init__` parameters with the class's
     `attrs` init parameters.
   - Compare attributes and nested classes the same way.
   - Add a slow `mypy.api` test on a snippet of accepted and rejected
     values. Pyright isn't in the dev environment, so either add it or
     check Pyright by hand.
6. **Keep generated `.py` files checked.** mypy reads a stub instead of the
   module beside it, so `mypy flopy4` stops checking generated module
   bodies. Add a CI step that runs mypy over them without stubs, or decide
   the drift test is enough, since they're mostly declarations.
7. **Ship `py.typed`, last and separately.**
   - Add it to package data.
   - First run mypy over `docs/examples` and fix what surfaces, since this
     exposes the hand-written API to users too.
   - Test against a built wheel in a clean environment: a source checkout
     doesn't show the missing-marker behavior.
8. **Clean up the docs.** Add a type-checking section to the user docs,
   correct the "Alternative" section in `mypy-converter-plan.md`, and remove
   the backlog's mypy item.

Pyright reads stubs without `py.typed`, so Pylance users benefit from step 3
on. mypy users of an installed package only benefit from step 7.

## Open questions

- **Does step 1 ship now?** Without it, Pylance users get no hints on
  constructor results and no false errors. With it, they get correct types
  and false errors on plain values. Recommend shipping it, because wrong
  types are harder to notice than a visible error, but it's a real
  trade-off.
- **Do record arguments take `str`?** `Record.convert` parses any string,
  so allowing it would let `Gwf(newtonoptions="garbage")` type-check.
  Recommend leaving it out at first, and treating it as a runtime-only form,
  as `TimeSeriesRef`'s docstring does for plain names. Add it for specific
  fields like OC's print formats if that proves annoying.
- **Do `legacy_kwargs` go in the stubs?** 26 classes have them. Recommend
  leaving them out. They're deprecated and warn at runtime, and a type error
  points people to the new name. Stubs then reject flopy3 keywords that
  work, so this should be weighed against the flopy3 migration story.
- **Attrs or pydantic?** The stubs assume attrs, and #282/#367 are still
  open. Settle that first: moving to pydantic would change the stub design.

## Costs

- A second generated file per module, 133 in all, though codegen writes both
  from one spec.
- `init_type` has to track what converters accept. A new plain form means
  changing the converter and the generator, with the step 2 tests catching
  a mismatch.
- Stubs override the real signatures, so any gap is a false error, which is
  why step 5 is required.
