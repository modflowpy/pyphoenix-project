# Binding parameters: the syntax sketch

Written 2026-11-05. This is step 4 of the [overview](overview.md#step-4-parameter-syntax-sketch),
and tests hypothesis H3. It's paper only: nothing here is in the schema. The binding check below
ran against the dev3 DFNs on devtools' `keyset-when` (`a83de97e`), and no real model has been
through it.

## Result

**Keep it, though it doesn't clearly meet the bar we set.** The overview said to keep the construct
if it came out smaller than the rules plus CellID `model`. It comes out about the same size, but it
covers references nothing checks today, and a second consumer can implement it from the spec.

- **Five components declare parameters, plus five exchanges,** with 17 declarations in all.
- **19 fields change.**
- **The rule registry goes from 4 to 3, not to 1** as H3 predicted.
- **`utl-ts`, `utl-tas` and `grid` need no parameter.** The overview had them in its table.
- **`when` and binding parameters aren't shown to be one construct.** Only `MODELNAMES` tests a
  parameter, and the co-occurrence rules don't fit.

## The construct

A component declares what it needs from whatever binds it:

```toml
# utl-spc
[params.target]
type = "package"
from = "row.pname"
rule = "no_advanced_transport"
```

- **`type`** is what the parameter names, using the selector grammar `parent` already has.
- **`from`** says where the value comes from. It's a table keyed by parent, or one source for all
  parents. A parent with no entry leaves the parameter unset.
- **`rule`** is optional, and means what it means on an `fk`: a named subset of the target.

`from` has three forms, and no lookup or search:

| Source | Meaning | Used by |
|---|---|---|
| `parent` | the component that binds this file | OBS |
| `row.<column>` | that column of the binding row, following its `fk` to an instance | SPC, SPCA, exchanges |
| `parent.<param>` | a parameter of the parent, passed down | MVR and GNC under an exchange |

### Referring to a parameter

A new `fk` attribute, `param`, replaces `path` in the earlier example. It says "look here":

```toml
fk = { param = ["model1", "model2"] }       # the value names one of these
fk = { param = "target", key = "bound" }    # the value is a key of this instance
```

| Considered | Why not |
|---|---|
| `fk = { path = "models" }` | Reads as a block and field |
| `fk = "params.models"` | Shorter, but it's still a path, and looks like a block called `params` |
| `fk = "^models"` | The sigil cut from #405. It says "context", not which parameter |

`scope` stays what it is, a sibling column. `param` is the same idea from outside the file.

## The rewrites

### MVR

```toml
# gwf-mvr
[params.model1]
type = "model"
from = { exg-gwfgwf = "parent.model1" }

[params.model2]
type = "model"
from = { exg-gwfgwf = "parent.model2" }

[blocks.options.fields.modelnames]
type = "keyword"
when = "model2"                             # was optional = true

[blocks.packages.fields.packages.item.fields.mname]
type = "string"
when = "modelnames"
fk = { param = ["model1", "model2"] }       # was path + rule = "exchange_models"
```

`mname1` and `mname2` change the same way. `pname` doesn't change, since it's still scoped by
`mname`, and an absent scope already means the current model.

**`MODELNAMES` doesn't go away,** as the overview said it would. MF6 still reads it, and rejects
a file where it disagrees with the binding, in both directions (`gwf-mvr.f90:785-798`). So it stays
in the file format, and `optional = false` with `when = "model2"` says it's present exactly when
the mover is an exchange's. A writer can then set it, and a user never needs to.

**Two names rather than `models`.** With `models` and a length, `when` needs an expression and a
cellid needs a position. With two names, `when` stays a plain name and a cellid's `model` does too.

### Exchanges and GNC

```toml
# exg-gwfgwf, and exg-gwtgwt, exg-gwegwe, exg-olfgwf, exg-chfgwf
[params.model1]
type = "model"
from = "row.exgmnamea"

[params.model2]
type = "model"
from = "row.exgmnameb"

# cellidm1
model = "model1"    # was "1"
```

The names live on `sim-nam`'s `exchanges` row, not in the exchange's own file, as the overview's
table implied. That's why a mover needs `parent.model1`: it's passed down one explicit step.

GNC declares what MVR declares, and its three cellids name `model1` or `model2`. Under a model
they're unset, which means the current model, as `model = None` does today. All 13 `model` sites
change only in value, and the comment explaining `"1"` and `"2"` goes.

### SPC and SPCA

```toml
# utl-spc
[blocks.period.fields.stress_period_data.item.fields.bndno]
fk = { param = "target", key = "bound" }    # was key + rule = "ssm_package"

# utl-spca
[params.target]
type = ["gwf-rcha", "gwf-evta"]
from = "row.pname"
rule = "no_advanced_transport"
```

This gives H4 with no new syntax. MF6 rejects list SPC on RCHA or EVTA, and array SPC on anything
else (`TspSpc.f90:353-375`). SPCA says so with `type`. SPC says so through `key`, since RCHA and
EVTA declare no `bound`. `keys.py` skips a component without the role today, and this needs it to
be an error, in this case at least.

### OBS

```toml
# utl-obs
[params.target]
type = ["model", "package"]
from = "parent"

[blocks.continuous.fields.continuous.item.fields.obstype]
fk = { param = "target", key = "observations" }
```

An exchange is a `package` by type, so `package` covers the slice's third case. `id` and `id2` stay
as they are, with the spec's existing sentence that the target's `observations` pick the arm. Only
OBS does this, so a general construct isn't justified.

**The hardest part of OBS needs no parameter.** The boundname arm is declared on the target, so
`when = "boundnames"` there resolves in the target's own options, using what `when` already does.
None of the boundname arms has it (217 at the top level, 211 fields once the seven lose theirs and LAK's and MAW's in ID2 are counted). It would express the third MF6 overrun
(`obs-boundname-overrun-fix.md`). **Seven components have the arm and no `BOUNDNAMES` option:**
`gwf-chdg`, `gwf-drng`, `gwf-evta`, `gwf-ghbg`, `gwf-rcha`, `gwf-rivg` and `gwf-welg`. That's a DFN
error: on all seven, MF6 writes no-data on release and overruns on a bounds-checked build.

### No parameter needed

- **`utl-ts`, `utl-tas`:** neither has an `fk`. References run from the parent's data into the
  file, so the file needs nothing from its binding.
- **`grid`:** a cellid already means the current model's grid. That's a useful way to think about
  conversions, and needs no syntax.

## What stays a rule

| Rule | Status | Why |
|---|---|---|
| `exchange_models` | Gone | |
| `ssm_package` | Shrinks to `no_advanced_transport` | MF6 skips SPC when an advanced transport package is paired with the flow package (`tsp-ssm.f90:195`). That comes from a sibling, not the binding |
| `flow_model` | Stays | Nothing that binds SSM supplies it. It comes from an exchange naming this model, or a budget file. `target` follows `pname`'s `fk` through it, so with a budget file SPC stays unchecked, as now |
| `mover_enabled` | Stays | Not about bindings. The overview counted it as replaced, but `keyset-when` kept it |

## Co-occurrence doesn't fit

The overview asked if MVR ⇒ MVT and LKT ⇒ LAK could use the same form. They can't:

- **MVR ⇒ MVT** depends on the flow model's components, reached through `flow_model`.
- **LKT ⇒ LAK** is a typed reference: `flow_package_name` must name a LAK. It defaults to the
  package's own name, and nothing binding LKT supplies it.

Writing `flow_model` as a parameter would need a reverse lookup among exchanges, which is `provides`
again. So these stay outside this construct. The claim that `when` and binding parameters are one
construct has one example, `MODELNAMES`. That doesn't refute it, and doesn't support it much.

## Why this isn't `^name` again

We cut `^name` and `provides` from #405 on 2026-11-02, as "dynamic scoping" that every consumer would
reimplement from prose, used by about four fields, and `binding = true` before that. The objection
was fair, so this has to differ in kind:

| | `^name` (cut) | `[params]` |
|---|---|---|
| Declared | No, used at the reference | Yes, on the component |
| How it resolves | Nearest binding row that has the name | One stated source per parent |
| Fallbacks | Lists, like `COALESCE` | None. Unset is declared by leaving out the parent |
| Checked statically | Loosely | Fully, see below |
| What the name means | Depends on where the file is bound | Fixed by the component |
| Fields using it | About 4 | 19, plus the checks below that have no field today |
| Relational reading | Correlated subquery | A column on the child's row, with a foreign key |

The test from that decision still applies: can a second consumer implement it from the spec alone,
and do enough fields use it?

**From the spec alone:** this is the whole resolver.

```python
def param(instance, name):
    source = instance.dfn.params[name].source_for(instance.parent.dfn)
    match source:
        case None:              return None
        case "parent":          return instance.parent
        case f"parent.{p}":     return param(instance.parent, p)
        case f"row.{column}":   return follow_fk(binding_row(instance), column)
```

`keys.py` has a separate search for each of these today: `_unbound` walks up to the nearest ancestor
with model references, and `_ssm_package` and `_binding_package` find the row.

**In relational terms,** which is what DDL generation needs:

| DFN | SQL |
|---|---|
| `[params.target]` on SPC | columns `flow_mname`, `flow_pname` on `spc`, as the slice has them |
| `fk = { param = ["model1", "model2"] }` | a composite key to `exchange_models (exchange, mname)` |
| `fk = { param = "target", key = "bound" }` | a foreign key to the `bound` supertype table |
| `when = "model2"`, `optional = false` | `CHECK (modelnames = (model2 IS NOT NULL))` |

## The check

`check.py` in this session's scratchpad wrote these declarations out and walked every file field in
the dev3 DFNs. It's a check on the sketch against the DFNs' structure, and doesn't resolve anything
in a real simulation.

| Component | Binders | Result |
|---|---|---|
| `utl-spc`, `utl-spca` | `gwt-ssm`, `gwe-ssm` | `pname` is on the row, with an `fk` |
| `gwf-mvr`, `gwf-gnc` | `exg-gwfgwf`, `gwf-nam` | Set under the exchange, unset under the model |
| `utl-obs` | 66 | `parent` always works |
| 5 exchanges | `sim-nam` | Both columns are on the row, with an `fk` |

There were no problems. A validator in the schema would check the same things, plus that each `fk`,
`model` and `when` names something declared. An exchange's cellid can then never fail to resolve, which
`^name` needed `COALESCE` for.

## Against the bar

| | Today | With parameters |
|---|---|---|
| Rules | 4 | 3 |
| Reference forms on `fk` | `path`, `key` | adds `param` |
| New attributes | | `[params]` with `type`, `from`, `rule`, and three source forms |
| CellID `model` | `"1"`, `"2"` and a comment | a declared name |
| OBS `target` | Not expressed | Declared |
| `obstype` checked against the target | No | Yes |
| Which model a cellid means | Prose | Declared and checked |

The grammar gets slightly larger, so it fails the bar as written. What it buys is coverage: `keys.py`
missed 22 broken OBS copies that MF6 rejects, and `Obs.target` is what lets it check them.

**What could still sink it:** using it. [Step 5](overview.md#step-5-binding-graph-navigation) is the
real test, since it runs on real simulations. If `Spc.target`, `Mvr.model1` and `Obs.target` can't
be written from this one resolver, the construct isn't what it claims to be.

## Decisions

- **`when` can test a parameter.** Decided 2026-11-05: it's a small step, and states MF6's two-way
  `MODELNAMES` check in one line.
- **The boundname fix goes first,** ahead of parameters. Tested, and written up in devtools'
  `obs-boundname-when-fix.md`. It confirmed all seven grid packages hit the same MF6 bug, so their
  arms are wrong, and should go.

Still open: **the rule on `target`.** `no_advanced_transport` keeps a rule for an edge case. Dropping
it is simpler, but would reject a bad `bndno` in a file MF6 ignores. I've kept it, since it's what MF6
does.
