# flopy4

`flopy4` (aka "FloPy 4" / pyphoenix) is a from-scratch reimplementation of
FloPy's MODFLOW 6 support. The MF6 object model is generated from MODFLOW 6's
DFN (definition) files via a codegen pipeline, rather than hand-maintained.
Status is pre-alpha/planning (see `pyproject.toml` classifiers) — APIs are
still shifting.

## Development environment

This project uses **pixi**, not bare pip/conda. Key tasks (see
`pyproject.toml`'s `[tool.pixi.tasks]` / `[tool.pixi.feature.*.tasks]`):

```
pixi run test                    # pytest -v -n auto (use for the full suite)
pixi run -e dev <cmd>             # run any command in the dev env (py3.11 + test + lint + build)
pixi run sync                    # flopy4 mf6 sync --verbose (sync flopy4.mf6 to discovered/latest MF6)
pixi run sync-status             # flopy4 mf6 status
pixi run generate-classes        # regenerate existing flopy4/mf6/ classes from modflow6 develop DFNs
pixi run generate-classes-preview # same, but also generates classes that don't exist yet
pixi run build-docs              # jupyter-book build docs/
pixi run install                 # pre-commit install --install-hooks
```

Test environments are split by Python version (`test311`/`test312`/`test313`,
solve-group per version) plus a combined `dev` environment. Always prefer
`pixi run ...` over invoking `python`/`pytest` directly — the pixi env pins
`numpy`, `netcdf4`, `proj`, etc. via conda, not just PyPI deps.

Linting: `ruff` (config in `pyproject.toml`, line-length 100), `mypy`,
`codespell`. Pre-commit hooks are installed via `pixi run install`.

## Repo layout

- `flopy4/mf6/` — the MF6 API itself.
  - `gwf/`, `gwt/`, `gwe/`, `prt/`, `exg/`, `utl/` — package classes, mostly
    codegen-generated from DFNs (a few, like `dis`/`disv`/`tdis`/`ncf`, are
    hand-written).
  - `codec/reader/`, `codec/writer/` — MF6 ASCII input file grammar/codec
    (lark-based reader, Jinja-based writer).
  - `converter/ingress/`, `converter/egress/` — structuring/unstructuring
    between parsed tokens and the attrs object model.
  - `spec.py` — the single source of truth for field-metadata conventions
    (`field()`/`path()`/`array()` carrying `block=`/`schema=`/`oc_action=`
    etc. as first-class kwargs). All components — hand-written or generated —
    use this one convention; do not reintroduce a second one.
  - `utils/codegen/` — the DFN → Python code generator (`make.py`,
    `filters.py`, `dfn2py.py`, Jinja templates).
  - `component.py`, `package.py`, `model.py`, `simulation.py` — core object
    model base classes.
  - `dimensions.py` — dimension resolution (lazy, runtime object-graph walk;
    see `sync-plan.md`/dimension design notes for rationale).
- `flopy4/spec.py`, `flopy4/adapters.py`, `flopy4/uio.py` — non-MF6-specific
  shared infrastructure.
- `test/` — pytest suite; `test/mf6/` covers codegen and the MF6 codec/object
  model specifically.
- `docs/` — Jupyter Book source (`docs/dev/` has older architecture docs —
  `sdd.md`, `srs.md`, `map.md` — treat these as historical/roadmap context,
  not necessarily current).

## MF6 object model rework (active work)

The project depends on `modflow-devtools` for DFN loading. The codegen path
has finished migrating off the legacy flat-TypedDict DFN module
(`modflow_devtools.dfn`) onto the pydantic-native, discriminated-union schema
(`modflow_devtools.dfns`, schema version `2.0.0.dev3`); `Column`/`Schema` are
gone and `Row` (`flopy4/mf6/row.py`) is the sole list-block schema. Active
work is now namefile loading (recursive structuring/binding resolution) on
top of that. **`mf6-object-model-plan.md`** at the repo root is the live
tracker for this effort (phases, status, decisions, next actions) — read it
before starting related work rather than assuming design intent. The codec
reader path (`flopy4/mf6/codec/reader/`) still uses the legacy `dfn` module
at schema version `dev1` — a known, independently-scheduled gap, not an
oversight. Other root-level `*-plan.md` files (`sync-plan.md`,
`protocols-plan.md`, `list-design.md`) describe settled, mostly-implemented
designs. The many root-level `*.txt` files are historical chat-log dumps from
earlier design discussions — useful for archaeology, not living
documentation.

General principle currently driving this work: prefer representations that
mirror the DFN's real structure over ad hoc flattening/special-casing that
accreted while the old schema couldn't express things like real discriminated
unions or list-of-record fields. When in doubt, check whether the new schema
already models something faithfully before adding a workaround.

## Conventions

- Don't add a second field-metadata or DFN-loading convention alongside an
  existing one "temporarily" — this codebase has actively been consolidating
  away from exactly that pattern (see Phase 0/0.5 in `mf6-object-model-plan.md`).
- Prefer devtools' own tree-walking/lookup helpers (e.g.
  `ComponentBase.get_fields(recurse=True)`, `get_block()`) over reimplementing
  equivalents in flopy4.
- Regenerating `flopy4/mf6/` classes after a codegen change: diff the
  regenerated output before committing; an unexpectedly large diff usually
  means a scope leak (e.g. mixing a mechanical schema-migration step with an
  API-shape redesign).
