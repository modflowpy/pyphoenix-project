## Update: reference polymorphism, and a broader framing

Since this was opened, we've run into polymorphism again from a different direction, while adding primary/foreign key metadata to the DFNs. (MODFLOW-ORG/modflow-devtools#405, #406 and #407 in the spec, #535 in flopy4). It's the same concept as above in a different representation. Below, I try to put both in one picture and say what that means for the spec and for flopy4.

### One concept, two representations

Polymorphism means one position (a field, a slot, a reference) can hold or point at things of more than one type. Programming languages offer a few ways to represent it, with different tradeoffs. The two that matter most here:

- **Sum types** (tagged or discriminated unions). The position holds the value itself, plus a tag saying which form it takes. The set of forms is closed and known up front.
  - Usability: tools can check that every form is handled, and can show users the alternatives. Adding a new form means updating everything that handles the type.
  - Cost, in languages with value types (C, Rust, Fortran): the value is stored inline, sized for its largest form plus a tag. There's no indirection.
- **Interfaces** (subtyping, protocols). The position holds a reference to something that lives elsewhere and promises certain behavior. The set of implementers is open.
  - Usability: anyone can add an implementer without touching the code that refers to it. In exchange, nothing can check that all cases are handled, and adding a new operation means updating every implementer.
  - Cost, in the same languages: each object is its own size, but there's a pointer to follow and a dispatch table to consult.

This tradeoff is known as the expression problem.

In Python the cost difference mostly disappears: every value is an object behind a reference, so a union-typed field and an interface-typed field both hold a pointer. What differs in Python, and so in flopy4:

- **Validation.** A pydantic discriminated union checks a value when it's assigned: it reads the tag, picks the form, and validates the fields. A polymorphic reference can only be checked once the whole simulation is loaded, by looking up the target and asking whether it plays the role.
- **Type hints and docs.** A union names its forms in the annotation, so editors, type checkers (`match` with `assert_never`) and generated JSON Schema all know them. A reference annotation can only say "a package name and a number"; which packages qualify lives in a registry.
- **What gets stored.** The real space difference is in the data, not the language. A variant stores its whole content in its form. A reference stores only a key, like `(pname1, id1)`. That keeps it small and free of cycles, but someone has to resolve it. A third form, **parametric** polymorphism (generics, e.g. `list[T]`), comes up below.

MODFLOW 6 input has both of the first two.

**Variants as sum types.** The post above is about this case. One concept takes one of several forms that MF6 defines: RCH or RCHA, a structured grid or a UGRID mesh. An option in the same input (`READASARRAYS`, the grid type) is the tag. The set is closed, since users don't invent new forms, so a sum type fits. In Python that's a pydantic discriminated union.

**References as interfaces.** #405 is about this case. In general terms:

- a value in one component refers to an entity in another component;
- the referrer doesn't fix the target's type, only what the target must be able to do;
- any component that declares it can play the required **role** can be the target, and it says which of its keys the reference uses.

The targets aren't alternatives to each other. They exist independently, and the referrer stores a pointer to one of them. The set is open: a new package that can play the role should be able to join without changing the referrer. So an interface fits. In Python that's a Protocol, or a registry from role to implementers.

The mover is the first case we hit. An MVR row stores `(pname1, id1)`: a package name and a number in that package. That's a pointer. `pname1` may name WEL, LAK, SFR or another package. Each of those declares whether it is a mover provider and what `id1` numbers in it: a bound for WEL, an outlet for LAK, a reach for SFR. Those declarations are the dispatch table. MF6 works the same way.

SPC's `bndno` shows the idea even more clearly. It means "boundary number *n* of the flow package this SPC file applies to". What a boundary *is* depends entirely on the target:

- for WEL or GHB, the *n*th entry, up to `maxbound`;
- for SFR or UZF, reach or UZF cell *n*;
- for LAK or MAW, lake or well connection *n*, numbered through every feature's connections in turn.

SPC itself knows none of this. It names the `bound` role, and each package says what its bounds are.

The cases we've found so far:

| Representation | Kind | Examples | Tag / pointer | DFN spec | Python |
|---|---|---|---|---|---|
| sum type | component variant | RCH/RCHA, EVT/EVTA, CHD/CHDG, SPC/SPCA | an option, or the file type | implied by naming only | discriminated union |
| sum type | row variant | SFR/LAK/MAW period settings, OC records | a keyword in the row | union records | union of item types |
| interface | reference | MVR `id1`/`id2`, SPC `bndno` | a key in another column (`pname1`) | `keys` roles + fk `key` (#405) | Protocol / registry |
| parametric? | grid / mesh type | structured vs. UGRID | the model's discretization | not yet | generic model type, e.g. `Model[Grid]` |

The last row is tentative. Switching a model from a structured grid to a UGRID mesh changes the shape of every array in it. That looks less like a sum type per component than a whole model parameterized by its grid type.

### Polymorphism vs. name resolution

Any reference answers two separate questions:

1. **What type of thing is the target?** If more than one type is allowed, the reference is polymorphic.
2. **Where do we look for it?** In other words, which instance, file or model to search for the key. This is name resolution.

The two are independent. #405 added roles for the first question and named **rules** for the second. A rule restricts the reference to a named subset of its target. Usually that subset depends on where the file is bound in the simulation, not on anything in the file itself, e.g. "one of the two models of the exchange that binds this mover". The target's type stays fixed.

In programming-language terms, roles are dispatch. Plain fk paths are lexical scope: the spec says where to look. Rules are closer to dynamic scope: the answer depends on where the file is bound in the simulation.

Examples of each combination:

| | target type fixed | target type varies (role) |
|---|---|---|
| **where to look is fixed by the spec**, or by a column in the same row | LAK period `lakeno` → `packagedata.ifno`; simulation `exgmnamea` → `models.mname`; MVR `pname1` → a `packages` row within model `mname1` | MVR `id1`: a `mover_provider` key of whichever package `pname1` names |
| **where to look depends on binding context** (a rule) | SSM `pname`: a package of the paired flow model (`flow_model`); exchange MVR `mname1`: one of the exchange's two models (`exchange_models`); exchange cellids: the grid of the exchange's first or second model (CellID `model = "1"`/`"2"`) | SPC `bndno`: a `bound` key of the flow package named by the SSM row that binds this SPC file (`ssm_package`) |

Most references fall in the top-left cell and need nothing new. Both new constructs are needed only for SPC `bndno`.

### Back to the original examples

The three examples in the post fit into this as follows:

- **List vs. layer-array vs. grid-array**: sum types (component variants).
- **Structured vs. UGRID mesh**: sum types per component, or parametric over the grid type.
- **ASCII files drive NetCDF contents**: whether a package's data lives in ASCII or NetCDF is a variant. That the ASCII file decides what NetCDF must contain is a cross-file condition, closer to a rule.

Going back to the decision-graph framing above: variants are the decisions, and references and rules are constraints between decisions made in different places. Choosing RCHA, for example, means an SPC can no longer refer to recharge boundaries by number.

### In the spec

A component declares which roles it can play, and what its key is in each:

```toml
# gwf-lak
[keys]
mover_provider = "outlets.outletno"
mover_receiver = "packagedata.ifno"

# gwf-wel, and other standard boundary packages
[keys]
mover_provider = "<=maxbound"
bound = "<=maxbound"
```

A foreign key names the role instead of a target path:

```toml
# gwf-mvr period id1 / id2
fk = { scope = "pname1", key = "mover_provider" }
fk = { scope = "pname2", key = "mover_receiver" }
```

The `[keys]` tables are the dispatch table from above, declared on the target side as MF6 does it. A new mover-capable package adds its own `[keys]` without touching MVR.

A rule is named on the fk, defined in prose in the spec, and implemented by consumers, like JSON Schema's `format`:

| rule | used by | meaning |
|---|---|---|
| `exchange_models` | MVR `mname`, `mname1`/`mname2` | one of the two models of the exchange binding this mover |
| `flow_model` | SSM `pname` | a package of the flow model the GWF-GWT/GWE exchange pairs with this transport model |
| `ssm_package` | SPC `bndno` (with role `bound`) | a bound of the flow package named by the SSM row binding this SPC file |

A consumer that doesn't implement a rule skips that check. Rules are kept for constraints that need the loaded simulation and touch only a few fields; they get their own syntax only once a second consumer needs it.

### How the two representations interact

- **The chosen variant decides which roles exist.** RCH declares the `bound` role and RCHA doesn't, because array input has no bound numbers for SPC to refer to. So variants and roles compose: variants are chosen per component, and roles attach to components. But the physical choice (list or arrays) leaks into the key structure. Nothing in the spec declares that SPCA goes with array variants and SPC with list variants.
- **Keys cross into row variants too.** SFR's diversion record, one form of a union period row, scopes its `idv` by the row's reach number `ifno`, which sits outside the variant. So sum types and references compose at the row level as well as the component level.
- **Option-conditional schema keeps coming up.** Some examples:
  - field `when` (MODFLOW-ORG/modflow-devtools#395: `petm0` only with `SURF_RATE_SPECIFIED`, `boundname` only with `BOUNDNAMES`);
  - mover roles (a package plays them only with `MOVER` set);
  - `READASARRAYS` selecting a variant;
  - `NETCDF` meaning a variable must exist in the model's NetCDF file.

  Each is "this part of the schema applies when option X is set". `when` now covers the first two; on a key set it reads:

  ```toml
  [keys]
  mover_provider = { path = "<=maxbound", when = "mover" }
  ```

  A package without `MOVER` then has no mover keys, so period rows naming it fail an ordinary key check.

  `READASARRAYS` and `NETCDF` turn out to be a different kind of thing. They choose how data is *written*, not which parts of the schema exist. In that respect they're like the `CONSTANT` / `INTERNAL` / `OPEN/CLOSE` array tags. See the option classification below.

### Where this leaves us

Open questions:

1. **Declare component variants explicitly?** Something like `variant_of = "gwf-rch"` plus the option that selects it, rather than relying on names. This would let consumers check pairings like SPCA → RCHA, and let docs show the alternatives together.
2. **Grid/mesh variation**: a variant per component, or a model-wide dimension parameter?
3. **One construct for option-conditional schema**, covering `when` and MOVER? `READASARRAYS` and `NETCDF` are layout and belong with the array tags (see below).
4. **How much belongs in the spec at all**, vs. runtime validation? The "second consumer" test above is a start. (A relational framing of the spec, and whether to split it into logical and layout layers, deserves its own discussion.)

On splitting the spec into layers, a first data point. We classified all 224 distinct option names in the DFNs by a re-encoding test. Toggle the option and re-encode the data to match: if the model is the same, the option is layout.

| Category | Distinct names |
|---|---|
| logical (model settings, schema, references) | 121 |
| output and other run directives | 82 |
| layout | 20 |
| both layout and logical | 1 (CSUB `HEAD_BASED`) |

So at the level of options, the split is clean.

One case was instructive. `AUXMULTNAME` (value × an aux column) could be re-encoded by multiplying the multiplier in, and MF6 would compute the same values. But MF6 applies the multiplier every time the value is used, and the aux column can be a time series. So the factorisation is a live rule, not an encoding. That points to a distinction the re-encoding test leaves out: some options *declare a derivation* rather than choosing a format. When every input to the rule is fixed (unit conversions, ratios to fixed cell thickness), the derivation can be materialised without loss, and the option is layout. When an input can change during the run, the rule itself is model content. This puts `AUXMULTNAME` with `AUXDEPTHNAME` and time series. A logical layer would need derived (generated) columns, and an editing tool like flopy4 should keep such rules rather than flatten them. The layout options aren't all plain syntax switches, though. Some can only be re-encoded using another component's data (`K22OVERK` needs the TVK schedule) or a model calculation (the CSUB initial-state options).

We also audited the constraints a valid simulation must satisfy, from formats and shapes through cross-package requirements ("MVR needs MVT", "CSUB needs `SS = 0` in STO"). MF6 has about 1,280 error and warning sites. We labelled a sample of 166 by kind, with these results:

- **The layering holds for constraints too.** The only constraints that seem to cross from layout into the model are conditions on where an encoding is defined. For example, `READASARRAYS` can't be combined with `SURF_RATE_SPECIFIED`, because the array form has nowhere to put PETM0. Those belong with the encoding.
- **Most of the contract is in the Fortran only.** The DFNs carry the grammar, shapes, required fields, and keys within a file. They carry almost no numeric ranges, option conflicts (NPF alone has seven), package co-occurrence rules, or geometric consistency checks such as `TOP > BOT`.
- **Conditional schema and binding context look like one construct.** `when` tests a package's own options. Many of MF6's conditions test other packages or the binding instead. `MODELNAMES` in MVR is the clearest case: it must be set exactly when the mover belongs to an exchange, so it restates the binding context as an option. That suggests giving `when` access to the binding, rather than adding a separate mechanism.
- **Most of what's logical fits relational constraints:** CHECK, keys, and multi-table assertions. The assertions are mostly joins against the grid. The few that don't fit are ordered sequences, stream-network acyclicity, and point-in-cell geometry.

Proposed next steps:

- **flopy4**:
  - separate classes for component variants (users write `Rcha`), discriminated at load by ftype and `READASARRAYS`, plus conversion between them; discriminated unions for row variants and typed slots;
  - the role registry and rule implementations (#535), extended to the newer spec features (`when` on key sets, keys scoped by enclosing records);
  - converting between variants (RCH↔RCHA, structured→UGRID) as a supported operation.
- **Docs**: decide which variant examples show by default, and present the alternatives side by side.
