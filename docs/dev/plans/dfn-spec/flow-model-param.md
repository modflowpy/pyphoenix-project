# `flow_model` as a parameter

Written 2026-11-11. A follow-up to devtools' `binding-params` branch, for a separate PR after it
merges. Nothing here is started.

## The situation

SSM's `sources.pname` and `fileinput.pname` name a package of the flow model paired with SSM's
transport model. Today that's the rule `flow_model`, which the spec defines in prose and consumers
implement in code.

The spec says why: "an exchange binds neither SSM nor any of its ancestors, so no parameter can
carry it." That's true, but it isn't the reason. The pairing is in `mfsim.nam`:

```
BEGIN models
  GWF6  gwf.nam  gwf_1
  GWT6  gwt.nam  gwt_1      <- binds the transport model; its siblings say nothing about gwf_1
END models

BEGIN exchanges
  GWF6-GWT6  flow.gwfgwt  gwf_1  gwt_1     <- the pairing
END exchanges
```

The path from the root to SSM is `mfsim.nam` → `gwt.nam` → SSM, and the pairing is in the first file
on it. So the parent binding the transport model has the information. It just isn't among the
binding's siblings: it's in another row of the same file, one that refers back to the model.

So `flow_model` isn't the collection attribute
[bindings-as-attribute-grammar.md](bindings-as-attribute-grammar.md) called it. Every exchange is in
`mfsim.nam`, so "the exchanges naming this model" is a query over the parent's own data, and an
inherited attribute whose equation sits at the `mfsim.nam` → model binding can say it.

## The idea

In function-call terms, a caller can compute an argument from its own state:

```python
class Simulation:
    def flow_model_of(self, name):
        for x in self.exchanges:
            if x.type in ("GWF6-GWT6", "GWF6-GWE6") and x.model2 == name:
                return x.model1
        return None

    GwtModel(name="gwt_1", flow_model=self.flow_model_of("gwt_1"))

class GwtModel:
    Ssm(flow_model=self.flow_model)  # passed on, as an exchange passes on its models
```

In the DFNs, that's a third kind of argument, a **back-reference**: rows of the parent that refer
to this binding's row, filtered by the component they bind, and a column to take from them.

```toml
# sim-nam models row
[blocks.models.fields.models.item.fields.mfname]
args = { flow_model = { from = "exchanges.exgmnameb", component = ["exg-gwfgwt", "exg-gwfgwe"], take = "exgmnamea" } }

# gwt-nam, gwe-nam packages row: pass it on
[blocks.packages.fields.packages.item.fields.fname]
args = { flow_model = "flow_model" }

# gwt-ssm, gwe-ssm
[params.flow_model]
type = "gwf-nam"

# sources.pname, fileinput.pname
fk = { path = "gwf-nam.packages.pname", param = "flow_model" }
```

The syntax is a first guess. `from` is a column of another list in the parent with an `fk` to this
binding's row, `component` filters by what that row binds (a GWT-GWT exchange names `gwt_1` as
`exgmnameb` too), and `take` is the column whose reference is passed.

What this gives:

- **The budget-file case is null.** With flows read from a budget file there's no exchange, so
  `flow_model` is unset, and `pname` isn't checked. That's what unset already means, so the
  spec's special case goes.
- **The spec states it and the validator checks it,** instead of consumers hand-coding a rule.
- **Rules mean one thing:** a named subset of the target. `no_advanced_transport` and
  `mover_enabled` stay rules. `flow_model` was the only rule about missing information.

## What it costs, and what to check

- **"Nothing is searched" bends.** It becomes "nothing outside the parent is searched." The query
  stays in one file, the caller's own, so scope is still lexical, but an argument stops being only
  a name. Decide whether that's acceptable before building it.
- **Uniqueness.** MF6 doesn't reject a second GWF-GWT exchange naming the same transport model.
  `exg-gwfgwt.f90` `set_model_pointers` (lines 124-129) sets `flows_from_file = .false.` and points
  the transport model's FMI at the flow model's `bndlist`, so a second exchange silently re-points
  it, and the last one read wins. `exg-gwfgwe.f90` (lines 122-126) is the same. The spec should
  make two an error: a back-reference argument must match at most one row, and the validator can't
  check that on DFNs alone, so it's a data check, as `pk` uniqueness is.
- **`{path, param}` is a new `fk` form.** `ForeignKey` allows `param` alone, or with `key`. Here
  the parameter picks the instance a path is looked up in, as `scope` does across components.
  Check that the validator's instance-picking logic for `scope` carries over.
- **Load order.** An MF6-order loader reads `mfsim.nam`'s models before its exchanges, so
  `flow_model` can only be set once `mfsim.nam` is fully read. That's true of the rule today, and
  [binding-navigation.md](binding-navigation.md#tasks) already has a task to check how flopy4
  orders it. Nothing gets worse.
- **PRT.** `exg-gwfprt.f90` sets `flows_from_file` too. PRT has no SSM, so nothing needs a
  `flow_model` there today, but the same argument would serve it.

## Tasks

- [ ] Decide whether the bend in "nothing is searched" is acceptable
- [ ] Settle the syntax for a back-reference argument
- [ ] Add it to `File.args` in `schema.py`, with validation: `from` is an `fk` to this binding's
  row's key, `component` admits only components that list's `file` can bind, and `take` has an
  `fk` whose target the parameter's `type` admits
- [ ] Allow `fk = {path, param}`
- [ ] In the dev2 migration (or dev3, if dev2 has shipped): `sim-nam` models row, `gwt-nam` and
  `gwe-nam` pass-on, `gwt-ssm` and `gwe-ssm` params and `fk`s. Drop the `flow_model` rule
- [ ] `dfnspec.md`: case 8 becomes a back-reference case, the Rules table loses `flow_model`, and
  the Parameters section gets the third argument kind and the uniqueness rule
- [ ] Regenerate snapshots and `schema.json`, and run the DFN tests
- [ ] flopy4: `flow_model` becomes a parameter on the resolver, and `Model.exchanges` is what
  computes the argument, not a lookup from SSM

## Predictions, written before looking

- The `scope` logic in the validator carries over to `{path, param}` with no new cases.
- No other reference in the DFNs needs a back-reference argument. If one does, that's evidence
  the form is general, not a one-off for `flow_model`.
- The flopy4 resolver needs no new machinery: `Model.exchanges` already computes the query, and
  the pass-on from `gwt-nam` to SSM is the same copy rule as exchange to mover.
