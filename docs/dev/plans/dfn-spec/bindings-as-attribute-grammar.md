# Bindings as an attribute grammar

Written 2026-11-11, for flopy4 development. The DFN spec's
[Bindings](https://github.com/MODFLOW-ORG/modflow-devtools/blob/develop/docs/md/dfnspec.md#bindings)
section (on devtools' `binding-params` branch until it merges) explains bindings with a function
call analogy. This note gives the more exact match, from compiler theory, and what it suggests for
[binding-navigation.md](binding-navigation.md). It isn't for the spec, whose readers needn't know
any of it.

## Attribute grammars, briefly

An attribute grammar (Knuth, 1968) attaches values, **attributes**, to the nodes of a tree, and
defines each one by an equation local to one node and its neighbours. Compilers use them for name
analysis and type checking: the tree is the parsed program, and the attributes say what each name
means and what type each expression has.

There are two directions:

- A **synthesized** attribute flows up: a node's value is computed from its children. An
  expression's type, from its operands' types.
- An **inherited** attribute flows down: a node's value is given by its parent, in the equation of
  the production that made the node. The symbol table an expression is checked against.

Two later extensions matter here:

- **Reference attributes** (Hedin, 2000) have values that are other nodes in the tree. Name
  analysis is the classic use: a variable use's `decl` attribute is its declaration node. They make
  a tree into a graph, without leaving the formalism.
- **Collection attributes** (Magnusson, Ekman and Hedin, 2007, building on Boyland's remote
  attributes, 2005) collect contributions from anywhere in the tree, such as "every call site of
  this method". They answer questions that run against the tree's structure.

Evaluation can be **demand-driven**: an attribute is computed when asked for, from its equation, as
in JastAdd. A grammar whose inherited attributes depend only on the parent and on siblings to the
left is **L-attributed**, and can be evaluated in one pass during parsing.

## The mapping

The simulation's input is a tree, built by bindings. Every concept in the spec's Bindings section
is one of the above:

| DFN | Attribute grammars |
|---|---|
| the simulation's files, bound into a tree | the syntax tree |
| a component | a nonterminal |
| a binding field (`file` with `component`) | a production: the parent's node has the child as a child |
| a parameter (`params`) | an inherited attribute of the child |
| `args` | the equations defining it, in that production |
| an argument naming the parent's own parameter (`model1 = "model1"`) | a copy rule |
| an unset parameter | an equation `:= null` |
| an `fk`, cellid or key-set reference | a reference attribute |
| key sets (`keys`), dimensions (`dims`) | synthesized attributes, read by references |
| a rule's subset (`mover_enabled`) | a predicate over attributes, a condition |
| `flow_model` | a collection attribute: exchanges contribute to their transport model |
| the spec's validator | a well-definedness check: every inherited attribute has an equation in every production |

Read with this, the cases in the spec are:

- **Cases 1 to 3** (a file alone; the row names the child; the row says more): the child has no
  inherited attributes. Its references resolve against its ancestors, which in attribute grammar
  terms are just reference attributes pointing up.
- **Case 4** (exchanges): inherited attributes, defined from the binding row's columns.
- **Case 5** (an exchange's GNC and MVR): copy rules.
- **Case 6** (GNC and MVR under a model): the same nonterminal in a production that defines its
  attributes as null.
- **Case 7** (SSM to SPC): an inherited attribute whose equation is a reference attribute of the
  parent's row, `fileinput.pname.decl`.
- **Case 8** (`flow_model`): not inherited, as the spec has it now, so treated as a collection
  attribute. But the production at the top of the path, `mfsim.nam` binding the transport model,
  does know it, from its own exchanges list. So it could be an inherited attribute whose equation
  reads the parent's data. See [flow-model-param.md](flow-model-param.md).

## Why explicit equations

There are two established ways to define inherited attributes:

- **Knuth's**: every production defines the inherited attributes of its children, explicitly. A
  parent that doesn't use an attribute still has to pass it on.
- **JastAdd's**: an inherited attribute's equation may sit at any ancestor, and the nearest one that
  defines it applies. This saves the copy rules, at the cost of a search up the tree.

flopy4's `keys.py` `_unbound`, which walks up to the nearest ancestor with references, is the
second. The sketch's `from` was a third thing, with the child naming where to look. The call-site
form is Knuth's. We chose it because each binding can then be checked on its own: a validator reads
one `file` field and knows what it passes, and one DFN says it all. The cost is the copy rules,
and there's one: an exchange passing its models to GNC and MVR. That's the trade the spec's
"nothing is searched" makes.

## What it suggests for flopy4

Each is a prediction or a design idea for [binding-navigation.md](binding-navigation.md), to check
there, not a decision.

- **The resolver is a demand-driven evaluator.** `param(component, name)` evaluates an inherited
  attribute from its equation, `args`, as JastAdd does. Its three cases are the equation kinds: a
  copy rule (the parent's parameter), a reference attribute (a row column's `fk`), or null.
- **Don't cache, at first.** Attribute grammar systems cache attributes, and then need incremental
  evaluation when the tree changes. flopy4's tree is mutable, and the chains here are at most two
  links long, so caching would cost more than it saves.
- **Loading is L-attributed, except for `flow_model`.** A parent's binding row is read before its
  child's file, so every parameter is available when the child loads, which is why
  `LoadContext.models` works at all. `flow_model` isn't: it depends on `sim-nam`'s exchanges, which
  an MF6 loader reads after models. So a load-time check of SSM's `pname` needs a second pass, or
  must wait until the simulation is built. Check how flopy4 orders this today.
- **`Model.exchanges` is the collection attribute.** It already collects the exchanges naming a
  model. `flow_model` is a lookup in it, and nothing else in the design needs a collection.
- **Synthesized attributes are already there.** `resolve_dims()` walks children for a dimension
  provider: a synthesized attribute, evaluated on demand. Key sets will be the same.
- **The SSM row question** ([binding-navigation.md](binding-navigation.md#the-ssm-row)) is about
  where case 7's equation reads its row from. In attribute grammar terms, the equation belongs to
  the production, so the child needs a link to the production, meaning its binding row. Name-file
  rows have that already, spread onto the child. That argues for the back-reference option.

## Terms, across the three vocabularies

| Spec | Function call | Attribute grammar | Relational |
|---|---|---|---|
| binding | call site | production | a row with a file column |
| parent | `self` | parent node | the component whose table holds the binding row |
| parameter | parameter | inherited attribute | a column carried onto the child's row |
| argument | argument | equation | a foreign key on the binding row |
| reference | name | reference attribute | foreign key |
| scope | scope | the attributes in reach | the joinable tables |
| scoped key | qualified name (`mname1::pname1`) | a reference attribute, looked up in another node | composite key |
| rule | built-in predicate | condition | a view |

## Reading

Checked 2026-11-11 against the publishers' and Lund University's records.

- D. E. Knuth, "Semantics of context-free languages", *Mathematical Systems Theory* 2(2):127-145,
  1968. doi:10.1007/BF01692511. The original: inherited and synthesized attributes.
- G. Hedin, "Reference attributed grammars", *Informatica* 24(3):301-317, 2000. Attributes whose
  values are nodes.
- J. T. Boyland, "Remote attribute grammars", *Journal of the ACM* 52(4), 2005.
  doi:10.1145/1082036.1082042. Attributes that depend on values far away in the tree, through
  references.
- E. Magnusson, T. Ekman and G. Hedin, "Extending attribute grammars with collection attributes:
  evaluation and applications", SCAM 2007, pp. 69-78. Collection attributes, in JastAdd.
- T. Ekman and G. Hedin, "The JastAdd system: modular extensible compiler construction", *Science
  of Computer Programming* 69(1-3):14-26, 2007. doi:10.1016/j.scico.2007.02.003. Demand-driven
  evaluation, and inherited attributes defined by the nearest ancestor.
- Kiama (Scala) and Silver are two other attribute grammar systems, if a working example helps.
