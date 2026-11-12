# Concepts and terminology

flopy4 draws its vocabulary from MODFLOW 6, xarray, scientific Python and
database design. This page says what its words mean and how they map to MF6 and
flopy3. The first half is for anyone using flopy4. The second is for people
working on it, or reading its design docs.

## Names in transition

This page uses the names flopy4 is moving to. Some of them haven't reached the
code yet, so until then use the name on the right.

| This page | In the code today |
|---|---|
| `to_xarray()` gives a `DataTree` for every component | a package gives a `Dataset` |
| `dense()` on the `grid` accessor | `to_xarray()`'s default for a list package |

## For users

### What a simulation is made of

| Term | Meaning | MF6 | flopy3 | flopy4 |
|---|---|---|---|---|
| **simulation** | The unit of work: one or more models, and how they're timed, solved and coupled | simulation, `mfsim.nam` | `MFSimulation` | `Simulation` |
| **model** | One simulated process on one grid, such as groundwater flow | model | `ModflowGwf` | `Gwf` |
| **package** | One input file's worth of a model or simulation, such as a stress or the grid | package | `ModflowGwfwel` | `Wel` |
| **utility** | A package that provides a capability rather than a hydrologic process, like observations or time-varying conductivity | utility | `ModflowUtlobs` | `Obs` |
| **exchange** | A connection between two models | exchange | `ModflowGwfgwf` | `Gwfgwf` |
| **solution** | The numerical solver for a set of models | solution, such as IMS or EMS | `ModflowIms` | `Ims` |

MF6 divides stress packages into two kinds. **Simple stress packages** (CHD, WEL,
DRN, RIV, GHB, RCH and EVT) can change their boundaries between periods.
**Advanced packages** (MAW, SFR, LAK and UZF) define their features once.

### Time

| Term | Meaning | MF6 | flopy3 |
|---|---|---|---|
| **stress period** | A division of a simulation's time. Period data is given by stress period. | stress period | stress period |
| **time step** | A division of a stress period that MF6 solves for | time step | time step, `kstp` |
| **`kper`** | A stress period's number in Python, starting at 0 | `iper` in a file | `kper`, also from 0 |
| **`iper`** | A stress period's number in an input file, starting at 1 | `iper` | |

So `stress_period_data={0: ...}` in Python writes `BEGIN PERIOD 1` in the file. MF6's
source also has a `kper`, which starts at 1. You'd only meet it reading the Fortran.

### How a package takes period data

MF6 has three **input forms**, plus the advanced packages' period blocks. flopy4
has a class for each form, since RCH and RCHA take different arguments. The file
type is the same (both are `RCH6`), and an option in the file says which form it
uses.

| Form | Option | Examples | flopy3 |
|---|---|---|---|
| **list-based** | none | `Wel`, `Chd`, `Rch` | `ModflowGwfwel`, `stress_period_data` |
| **layer array-based** | `READASARRAYS` | `Rcha`, `Evta` | `ModflowGwfrcha` |
| **grid array-based** | `READARRAYGRID` | `Welg`, `Chdg` | `ModflowGwfchdg` |

Once a block has been given, a period with no block carries on from the last one, in
every form. Blocks that are present behave differently, so changing a package's form
can change what your input means:

| Form | A new block | Not given in the block | An empty block |
|---|---|---|---|
| list-based, and MVR | replaces all entries | removed | clears all entries |
| layer array-based | replaces the arrays it names | keeps its value | doesn't turn anything off, so give a rate of zero |
| grid array-based | replaces the arrays it names | keeps its value, by position | clears all entries |
| advanced | changes only what it names | keeps its setting | changes nothing, so deactivate through settings |

### What a row refers to

| Term | Meaning | Addressed by | Stays the same across periods? |
|---|---|---|---|
| **feature** | A thing an advanced package defines once, such as an SFR reach, a lake, a multi-aquifer well or a UZF cell | its number, `ifno`, declared in PACKAGEDATA | yes |
| **list entry** | A row in a list-based period block | its position in that block | no |
| **grid entry** | A cell with a stress in a grid array-based block | its position among the block's cells with a value, in node order | no |
| **boundname** | A label on a row, enabled by `BOUNDNAMES` | not an address | see below |

Entry numbers can change meaning between periods. Boundary 2 can be one well in
period 1 and another in period 2, so MVR and SPC rows that use a number have to
match that period's order. If you insert, delete or reorder a period's rows, check
anything that refers to them by number.

A boundname isn't an ID. Several rows can share one, and a flow observation of a
boundname reports their sum.

A layer array has no entries at all. It has one value per vertical column of the
grid (`ncpl`), and nothing refers to one by number.

### Xarray

| Term | Meaning |
|---|---|
| **`to_xarray()`** | Exports a component to xarray as it's held: what you gave, in the periods you gave it. A list stays a table of rows. `from_xarray()` reads it back. |
| **`dense()`** | Computes the array you'd usually want to plot or do arithmetic on: values placed on the grid, for every period. It's computed from the export, and isn't stored. |
| **`kper`** | The period dim of a dense array. In a table of rows, a coordinate saying which period each row is in. |
| **`entry`** | A period list's row dim, one entry per row, with `kper` as a coordinate on it. |
| **`<name>_kper`** | The periods given for one array, as in `recharge_kper`. Each array has its own, since each can be given in different periods. |

### Other terms you'll meet

| Term | Meaning | Note |
|---|---|---|
| **name file** | The file listing a simulation's or a model's components | Two words, as in mf6io. |
| **cellid** | A cell's address: layer, row and column on DIS, layer and cell on DISV, node on DISU | Written from 1 in a file. |
| **user node**, **reduced node** | A cell's number counting every cell, and counting only cells left in the grid by `IDOMAIN` | Inputs use user nodes. |
| **`x_world`**, **`y_world`** | A cell's coordinates after the grid's origin and rotation are applied. `x` and `y` are local to the grid. | MF6 gives `XORIGIN`, `YORIGIN` and `ANGROT`. flopy3 calls local coordinates "model coordinates". |

## For developers

### Choosing a term

Prefer, in order:

1. **MF6's term,** if it has one. Users read mf6io.
2. **A domain standard** (CF, UGRID, xarray, SQL), at that domain's boundary.
3. **An established theory term,** in design docs only, never in user docs.
4. **A new word,** only with a definition here.

Lead with a plain statement, and give a theory term once in parentheses. Drop it if
it doesn't help settle a real question.

### Glossary

| Term | Meaning | MF6 | flopy3 | Theory |
|---|---|---|---|---|
| **DFN** | A definition file: the spec for one kind of input file, such as `gwf-wel` | DFN | DFN | |
| **component** | A node in a simulation's tree. Each kind has one DFN. | differs: in IDM, `component` is `GWF` and `subcomponent` is `RCHA`, and SPC is the "Stress Package Component" | | |
| **`WorkspaceComponent`** | A component with a workspace, namely a simulation or model. A model under a simulation uses the simulation's. | | | |
| **field** | A variable on an attrs class or in a DFN. For a value spread over cells, say "gridded quantity". | variable | variable | |
| **`ftype`** | flopy4's one attribute for a component's file type | `ftype`, `mtype`, `exgtype`, `slntype` | | |
| **`bound`** | The role of a package whose rows are boundaries. In prose say feature, list entry or grid entry. | `bound`, `nbound` in source | | |
| **binding** | The row or option in one file that attaches a component to the simulation: a `PACKAGES` row, or `OBS6 FILEIN` | | | |
| **binding arguments** | What the binding knows and the file doesn't, like which two models an exchange connects | | | |
| **layout** | How an MF6 file writes things down: blocks, keywords, arrays or lists, `CONSTANT`, `OPEN/CLOSE`, unit factors | | | physical schema |
| **logical** | What the data is: tables, columns, keys, and settings that change what the model computes | | | logical schema |
| **runtime memory** | MF6's own variables, as listed in the DFN memory catalog. A level, but not the logical one. | memory | | |
| **label** | What an option is. **Layout**: re-encoding the data to match leaves the model unchanged. **Logical**: describes the model. **Directive**: changes only what's run, printed, saved or checked. **Mixed**: only CSUB's `HEAD_BASED`. | | | |
| **`schema` option** | An option that decides which logical columns or tables exist, or what other components can refer to. `AUXILIARY` adds columns, `BOUNDNAMES` adds a name column others can refer to, and `SORPTION` decides which arrays exist. It's an attribute some options carry, separate from their label. | | | row polymorphism, dependent record |
| **layout preservation** | The rule that the object model holds input as given, layout included, and logical forms are views over it | | | concrete vs. abstract syntax (an analogy) |
| **view** | Something computed from held data and never stored. Say whether it's read-only or two-way. | | | external schema |
| **lens** | A two-way mapping between a layout and the logical relation. Its **get** reads the view, and its **put** writes an edit back. Its **complement** is what the view lacks and `put` needs. It's **partial** if some logical content has no form in that layout, as with two RCH rows in one vertical column under RCHA. | | | lens, with its laws |
| **observation** | What logical content is judged against: results, what can be referred to, metadata a conversion must keep, and results after a permitted edit | | | observational equivalence |
| **stage** | When a derivation's result is fixed: **constant** (unit factors), **edit** (`STORAGECOEFFICIENT`, safe to compute at write time only), or **run** (`AUXMULTNAME`, TS, TAS). Say "fixed at", not "bound at", since binding means something else here. | | | binding-time analysis |
| **snapshot**, **delta** | A list block is a snapshot, carried until replaced. An advanced block is a delta. | | | step function at change points |
| **sparse table** | A union record's rows read as one logical row, as with `1 STATUS INACTIVE` and `1 RATE 0.1` | keystring | | entity-attribute-value |
| **representation** | flopy4's xarray form of a simulation. Files and other libraries' conventions are adapters over it. | | | |
| **NetCDF profile** | One way the representation is written to NetCDF. The **grouped archive** has a group per component, and MF6 doesn't read it. **MF6 NetCDF** is ungrouped, and MF6 does. | | | |
| **type tag** | The marker saying what kind of component an exported node holds | | | |
| **discriminator** | What selects among variants: a union row's keyword, or `READASARRAYS` for a class | | | sum type, with arms |
| **key domain** | The set of values a key can take, such as `<=maxbound` | | | bounded index |
| **sync** | `flopy4 mf6 sync`, which regenerates the classes from an MF6 version's DFNs. **Sync contract**: the `_contract.py` it writes, recording the version, DFN commit and generated files. | | `flopy.mf6.utils.generate_classes` | |

### One word, one sense

These words have carried several meanings. Use the bare word only for its main
sense, and the other wording for the rest.

| Word | Bare, it means | Otherwise say |
|---|---|---|
| layout | MF6 file layout | "NetCDF profile"; "cell indexing"; "row format"; "memory arrangement" |
| package | an MF6 package | `mf6xr` (working name) for the planned Python package |
| spec | never used bare | "DFN spec"; "representation spec" |
| view | computed from held data | "SQL view"; "row proxy" for a row object over `ItemTable` |
| context | never used bare | "binding arguments"; `WorkspaceComponent`; "`RowContext`"; "memory context" |
| rule | never used bare | "named rule" in a DFN; "layout preservation"; "rewrite rule" in the codemod; "constraint" for what a valid simulation must satisfy |
| tag | never used bare | "tagged" for the DFN key; "type tag"; "discriminator"; "option attribute" for `binding` and `schema` |
| contract | never used bare | "sync contract"; "data contract"; "import-linter contract"; "input constraints" |
| schema | never used bare | "DFN schema version"; "`schema` option"; "representation" for the export; "database schema" |
| level | layout, logical or runtime | "site" for where a discriminator sits |
| dynamic | the DFN's `dynamic` key, for a keyword whose value comes from its `fk` | stage words for derivations (see above) |
| kind | qualified only | "key domain" for keys; "constraint kind"; "lens kind" |
| field | an attrs or DFN field | "gridded quantity" |
| layered | use the keyword, `LAYERED` | "cell indexing" for layered or flat |
| row, entry | row for tables; entry for an MF6 boundary row, as mf6io says | `Item` and `Record` keep their class names; a "control record" is MF6's array header |
| fill forward | what happens for a period with no block | for what a new block does, say replace or update |

### Equivalence

These names say exactly what a gate or test checks, so use the one you mean.

| Name | Holds when |
|---|---|
| **object-equal** | `==` on components |
| **text-equal** | files are the same bytes, perhaps up to whitespace |
| **layout-equal** | same blocks, options, control records and external-file choices |
| **logically equal** | same after normalizing by the option labels |
| **result-equal** | MF6's heads and budgets agree within a stated tolerance |

"Round trip" alone is ambiguous, since it has meant both load, write and load, and
load, write, run and compare. Say which.

### Type vocabulary

The design docs use these for what varies in MF6 input, and what decides it.

| Construct | Example | Theory |
|---|---|---|
| a reference whose target depends on another value | MVR's `(pname1, id1)` | dependent pair |
| a component that depends on its binding | SPC's target package | dependent function, ML functor |
| array shape that depends on the grid | griddata | shape polymorphism |
| wrapping a value type | periodic data, a value or a time series name | parametric type constructor |
| accepting many forms of one thing | a row as a tuple or a dict | coercion |
| a numeric range | `k > 0` | refinement type |
| missing values | inapplicable vs. not given | Codd's marks |

## Acronyms

| Acronym | Meaning |
|---|---|
| MF6 | MODFLOW 6 |
| DFN | definition file |
| IDM | MF6's Input Data Model, which loads input into memory |
| MVP, MMP, GA | minimum viable product, minimum marketable product, general availability: flopy4's [milestones](map.md) |
| SRS, SDD | [software requirements specification](srs.md), [software design description](sdd.md) |
| DIS, DISV, DISU | structured, vertex and unstructured discretization |
| TDIS | time discretization |
| IMS, EMS | iterative and explicit model solution |
| GRB | binary grid file |
| HDS | binary head file |
| CBC | cell-by-cell budget file |
| ATS | adaptive time step utility |
| TS, TAS | time series, time-array series |
| TVK, TVS | time-varying hydraulic conductivity, time-varying storage |
| OBS | observations utility |
| NCF | model NetCDF utility |
| HPC | high performance computing utility |
| MVR | water mover |
| GNC | ghost-node correction |
| SSM | source and sink mixing |
| SPC, SPCA | stress package component, list-based and array-based |
| BMI, XMI | Basic Model Interface, and MF6's extended form of it |
| CF, UGRID | Climate and Forecast conventions, the unstructured grid conventions, both for NetCDF |

## Project shorthand

| Term | Meaning |
|---|---|
| `flopy4` | The Python package in this repo, code name pyphoenix |
| FloPy 4 | The product the [SRS](srs.md) and [SDD](sdd.md) describe |
| flopy 4.x | The flopy release series `flopy4` is to merge into |
| flopy3 | flopy 3.x, including its `flopy.mf6` |
| legacy engine | flopy3's MF6 data layer, if it's kept as `flopy.mf6.legacy`. It would be frozen and wouldn't sync. Whether to keep it is open. |
| compat layer | What keeps flopy3 code working on the new engine in 4.x: generated `ModflowXxx` names, and handwritten pieces for the simulation and model |
| `Legacy` | A flopy3 constructor keyword flopy4 still takes, with a warning |
| codemod | `flopy4 migrate`, which rewrites flopy3 code |
| registry corpus | The models in modflow-devtools' registry, used as test input |
| tier A-E | The test tiers for 4.x. A: shared code. B: old engine internals. C: compat scoreboard. D: new engine. E: equivalence between the engines. |
| scoreboard | Tier C: how much flopy3 code and how many MF6 autotests and examples pass on the compat layer. It reports and doesn't gate. |
| Track A-G | The work in the [MMP plan](mmp-plan.md): engine correctness, API decisions, data and xarray, docs, migration, 3.x prep, packaging |
| dev3 | The DFN schema version `2.0.0.dev3` from modflow-devtools |
| materialize | In benchmarks, reading everything a load deferred. In the design docs, computing a derivation and storing the result. Say which. |
| FUNC-*n*, NFR-*n*, SYS-*n* | Requirements in the [SRS](srs.md) |
