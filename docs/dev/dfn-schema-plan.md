# DFN schema formalization plan

This document captures the current state of the DFN specification and outlines steps to formalize it.

## Background

The MODFLOW 6 definition file ("DFN") format has evolved to suit MF6's needs. It is a simple text format described in [natural language](https://modflow6.readthedocs.io/en/latest/_dev/dfn.html). The schema is implicit in this description and in the content of the existing DFN files, which must be read with an understanding of DFN format in the context of the MF6IO documentation.

We can call the existing schema "v1". Its content is faithfully parsed from DFN files, with no alterations. Currently v1 is consumed by tooling in the MF6 repository.

A slightly normalized version of the v1 schema can be generated from the v1 DFN files by the `modflow_devtools.dfn` module and consumed by flopy 3.x codegen, serializing to/from TOML. We call this schema "v1.1". It parses bools, resolves `common.dfn` substitutions, drops some attributes, and does some structural transforms. Flopy 3.x should be altered soon to consume either v1 or v2. v1.1 only exists due to poor planning on my part (WPB).

A more substantially transformed schema version has been grown on the fly as flopy 4.x / development proceeds. We have not yet formally specified this version, just implemented the transforms in the `modflow_devtools.dfns` module (note the plural; this is distinct from the old `dfn` module, which will be retired with devtools v2). The schema therefore exists implicitly as whatever falls out of those transforms. This document makes this new schema explicit. It can be released as "v2" simultaneous with the next major version (v2) of devtools.

Note: `flopy4/mf6/codec/reader/dfn2lark.py` already imports from `modflow_devtools.dfns` (v2), not the old `dfn.py` module.

## Principles

**Schema versioning.** Allows adding/removing from the schema in a disciplined way. 

**Schema validation.** Allows checking if a given component specification conforms.

**Conceptual/nominal clarity.** The first distinction to make is between schema and serialization format. The content of DFN files could be written instead to TOML, YAML or JSON. That content, i.e. the schema, describes the shape and characteristics of data: what components exist, what properties they have, how they are connected, etc. In other words, structural information, defining the valid structure of each simulation component.

**Separation of concerns.** 

DFN files carry not only structural information, but also input file format information. This is a consequence of the MODFLOW 6 input data model's design. A DFN file represents an input component in the context of MODFLOW 6's type system, which is closely coupled to the MODFLOW 6 input format. For instance, until recently, MODFLOW 6 packages required all array data to be specified in sparse list-based format. Recent work has introduced format variants for arrays, but these are baked into distinct component definitions, rather than a single component definition supporting multiple variants for each array field.

Ideally, the MF6 input specification could be agnostic to any particular input format: the schema describing the input data model abstractly, with format information derived from the schema or expressed as optional format attributes coexisting in the component definition. The former, derivation from the schema via a well-defined set of rules, is ideal, though the latter is acceptable if needed, though concerns should be carefully isolated by naming discipline and selective presence.

**1 DFN file per input component.** DFN files do not map 1-1 to hydrologic processes. A DFN file describes a single way of representing a process, not necessarily the only one. Where multiple DFN files represent the same process in different formats (e.g. `gwf-wel`/`gwf-welg`, `gwf-rch`/`gwf-rcha`), the relationship is made explicit via `Dfn.variant_of: str | None`. Unification of format variants is deferred to a future version of the schema.

**Explicit parent-child relationships.** Parent-child relationships are intrinsic to a component's identity, and should be explicitly defined in the specification. Two parent relationship types are distinguished: fixed and free. For fixed-parent relationships, a component declares its own parent with `Dfn.parent`. A component compatible with several potential parents (historically called a "subpackage") may omit the `parent` attribute. Parents may signal that they can contain subpackages with `Dfn.accepts`, a list of names of the subpackage components. A connectivity graph can be derived from these attributes.

## Approach

`modflow-devtools` provides utilities for working with (and converting between) schemas.

Define the new schema in the `modflow_devtools.dfns` module, using [Pydantic](https://pydantic.dev/docs/). This gives us JSON Schema for free, plus validation utilities.

TOML is the tentative choice for serialization, though it's trivial to switch to YAML or JSON, should we want to.

MODFLOW 6 consumes definition files to generate Fortran source as well as documentation. We will at some point need to rewrite MF6 tooling to use the new v2 schema specification.

`flopy` consume definition files to generate Python source compatible with MF6. `flopy` 4.x should consume schema version 2+. As stated above, flopy 3.x codegen consumes v1.1, but should be rewritten to use v1 or v2+, at which point we can dispose of v1.1.

## Related

- `modflow-devtools` #262 — DFNs API (needs stable schema versioning)
- `modflow-devtools` #259 — schema naming discussion
- `modflow-devtools` #233 — separated format from schema version
- `pyphoenix-project` #246 — separate structural from format spec
- `pyphoenix-project` #282 — consider pydantic
- `pyphoenix-project` #205, #206, #218 — specific schema issues to resolve before finalizing
- `modflowpy/pyphoenix-project` discussion #47 — DFN schema/format (TOML design)

## Next steps

Study existing DFNs to derive a complete ruleset by which format behavior can be inferred from or validated against the structural schema. This includes block-level input style (derivable from block composition) and field-level format annotations (some inferrable, some requiring explicit storage). See `dfn_format_rules.md` for the working analysis.

Once the ruleset is complete and verified against the DFN corpus, formalize the v2 schema. Implementation details, including the Pydantic field hierarchy, attribute lifecycle decisions, and transform spec, are tracked in `dfn_refactor.md` and `dfn_steps.md`.
