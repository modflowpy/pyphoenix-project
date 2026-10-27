# FloPy 4 software requirement specifications (SRS)

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Introduction](#introduction)
  - [Product scope](#product-scope)
  - [Product value](#product-value)
  - [Intended audience](#intended-audience)
  - [Intended use](#intended-use)
  - [Use cases](#use-cases)
- [Requirements](#requirements)
  - [Functional requirements](#functional-requirements)
  - [Non-functional requirements](#non-functional-requirements)
  - [System requirements](#system-requirements)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## Introduction

This is the Software Requirement Specifications (SRS) document for FloPy 4. It covers the product as a whole, through general availability (GA). The milestones are described in the [roadmap](map.md).

### Product scope

FloPy 4 can create, load, write, and run MODFLOW 6 simulations, and access their results. The first milestone, the minimum viable product (MVP), covers reading and writing MODFLOW 6 input files and running MODFLOW 6. Later milestones add pre- and post-processing, performance work, and feature parity with FloPy 3.x.

### Product value

The MVP delivers a basic set of functionality which will become the core of FloPy 4. Later milestones build on that core until FloPy 4 can replace FloPy 3.x.

### Intended audience

The MVP is an internal product for use by the MODFLOW 6 and FloPy development team, as well as external collaborators. The audience widens with each milestone: initial USGS and Deltares testers at the MVP, a wider test audience at the MMP, and all FloPy users at GA.

### Intended use

FloPy 4 is a library supporting the functionality described above. The MVP is developer-facing.

Other libraries and tools may build upon FloPy 4 to offer more advanced, domain-specific, or application-specific functionality.

## Requirements

Requirements are prioritized according to the [MoSCoW method](https://en.wikipedia.org/wiki/MoSCoW_method), indicating which requirements the product Must, Should, Could, and Won't include. Each requirement also names the milestone (MVP, MMP, or GA) by which it should be met.

### Functional requirements

| ID      | Description | MoSCoW | Milestone |
| ------- | ----------- | ------ | --------- |
| FUNC-1  | The product can read and write MODFLOW 6 input files, both ASCII and binary. | M | MVP |
| FUNC-2  | The product can read MODFLOW 6 output files. | M | MVP |
| FUNC-3  | The product can run MODFLOW 6 simulations and provide access to their results. | M | MVP |
| FUNC-4  | The product can programmatically create, access, and manipulate MODFLOW 6 simulations. | M | MVP |
| FUNC-5  | The product supports existing MODFLOW 6 discretization types and can be extended to support new ones. | M | MVP |
| FUNC-6  | The product allows simulation subcomponents to be created independently of parent context, then combined programmatically. | M | MVP |
| FUNC-7  | The product can round-trip (i.e. load, write, and run) an existing simulation and give identical results to previous runs. | C | MVP |
| FUNC-8  | The product can manage larger-than-memory models and datasets. E.g., the product can be used to create an example model of the United States with a **?1 km?** grid resolution. | M | MMP |
| FUNC-9  | The product can determine and report whether it is compatible with a given MODFLOW 6 version (and corresponding specification). | M | MVP |
| FUNC-10 | The product is compatible with a wide range of MODFLOW 6 versions (and corresponding specifications). | S | MMP |
| FUNC-11 | The product supports spatial and temporal units to the extent that MODFLOW 6 does. | C | MMP |
| FUNC-12 | The product can generate a MODFLOW 6 interface layer (i.e. source code) from definition files. | M | MVP |
| FUNC-13 | The product's MF6 interface layer can be inspected at runtime, e.g. to discover component attributes and variables. | M | MVP |
| FUNC-14 | The product's MF6 interface layer can reproduce the specification used to generate it. | S | MMP |
| FUNC-15 | The product provides appropriate, informative string dumps for simulation components. | M | MVP |
| FUNC-16 | The product provides programmatic access from any component to any other component registered with the simulation. | S | MVP |
| FUNC-17 | The product allows specifying the precision with which values are written to input files. | M | MVP |

### Non-functional requirements

| ID      | Description | MoSCoW | Milestone |
| ------- | ----------- | ------ | --------- |
| NFR-1   | The product's documentation makes a clear distinction between public and internal APIs. | M | MMP |
| NFR-2   | The product behaves unsurprisingly, with reasonable defaults for common APIs and use cases. | M | MVP |
| NFR-3   | The product provides clear and informative error messages to the user when an error occurs. | M | MVP |
| NFR-4   | The product has consistent APIs for MODFLOW 6 and older MODFLOW programs. | S | GA |
| NFR-5   | The product can be easily extended e.g. to support new input/output file formats. | S | MVP |
| NFR-6   | The product provides a well-documented, type-hinted public API. | S | MMP |
| NFR-7   | The product consolidates entry points and emphasizes API discoverability. | S | MMP |

### System requirements

| ID      | Description | MoSCoW | Milestone |
| ------- | ----------- | ------ | --------- |
| SYS-1   | The product complies with scientific-python.org guidelines: <https://scientific-python.org/specs/spec-0000/>. This ensures compatibility with other libraries in the scientific python ecosystem on which the product depends. | M | MVP |
| SYS-2   | The product runs on the following operating systems: Windows, Linux, MacOS. | M | MVP |
| SYS-3   | The product is available on the Python Package Index (PyPI) and conda-forge. | M | GA |
