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

This is the Software Requirement Specifications (SRS) document for the FloPy 4 minimum viable product, called the MVP.

### Product scope

The MVP will be able to load, write, and run MODFLOW 6 simulations.

### Product value

The MVP delivers a basic set of functionality which will become the core of FloPy 4.

### Intended audience

The MVP is an internal product for use by the MODFLOW 6 and FloPy development team, as well as external collaborators.

### Intended use

The MVP is a developer-facing library supporting the core functionality describe above.

Other libraries and tools may build upon the MVP to offer more advanced, domain-specific, or application-specific functionality.

## Requirements

Requirements are prioritized according to the [MoSCoW method](https://en.wikipedia.org/wiki/MoSCoW_method), indicating which requirements Must, Should, Could, and Won't be included in the first iteration.

### Functional requirements

| ID      | Description | MoSCoW |
| ------- | ----------- | ------ |
| FUNC-1  | The product can read and write MODFLOW 6 input files, both ASCII and binary. | M |
| FUNC-2  | The product can read MODFLOW 6 output files. | M |
| FUNC-3  | The product can run MODFLOW 6 simulations and provide access to their results. | M |
| FUNC-4  | The product can programmatically create, access, and manipulate MODFLOW 6 simulations. | M |
| FUNC-5  | The product supports existing MODFLOW 6 discretization types and can be extended to support new ones. | M |
| FUNC-6 | The product allows simulation subcomponents to be created independently of parent context, then combined programmatically. | M |
| FUNC-7 | The product can round-trip (i.e. load, write, and run) an existing simulation and give identical results to previous runs. | C |
| FUNC-8 | The product can manage larger-than-memory models and datasets. E.g., the product can be used to create an example model of the United States with a **?1 km?** grid resolution. | M |
| FUNC-9 | The product can determine and report whether it is compatible with a given MODFLOW 6 version (and corresponding specification). | M |
| FUNC-10 | The product is compatible with a wide range of MODFLOW 6 versions (and corresponding specifications) | S |
| FUNC-11 | The product supports spatial and temporal units to the extent that MODFLOW 6 does. | C |
| FUNC-12 | The product can generate a MODFLOW 6 interface layer (i.e. source code) from definition files. | M |
| FUNC-13 | The product's MF6 interface layer can be inspected at runtime, e.g. to discover component attributes and variables. | M |
| FUNC-14 | The product's MF6 interface layer can reproduce the specification used to generate it. | S |
| FUNC-15 | The product provides appropriate, informative string dumps for simulation components. | M |
| FUNC-16 | The product provides programmatic access from any component to any other component registered with the simulation. | S |
| FUNC-17 | The product allows specifying the precision with which values are written to input files. | M |

### Non-functional requirements

| ID      | Description | MoSCoW |
| ------- | ----------- | ------ |
| NFR-1   | The product's documentation makes a clear distinction between public and internal APIs. | M |
| NFR-2   | The product behaves unsurprisingly, with reasonable defaults for common APIs and use cases. | M |
| NFR-3   | The product provides clear and informative error messages to the user when an error occurs. | M |
| NFR-4   | The product has consistent APIs for MODFLOW 6 and older MODFLOW programs. | S |
| NFR-5   | The product can be easily extended e.g. to support new input/output file formats. | S |
| NFR-6   | The product provides a well-documented, type-hinted public API. | S |
| NFR-7   | The product consolidates entry points and emphasizes API discoverability. | S |

### System requirements

| ID      | Description | MoSCoW |
| ------- | ----------- | ------ |
| SYS-1   | The product complies with scientific-python.org guidelines: <https://scientific-python.org/specs/spec-0000/>. This ensures compatibility with other libraries in the scientific python ecosystem on which the product depends. | M |
| SYS-2   | The product runs on the following operating systems: Windows, Linux, MacOS. | M |
| SYS-3   | The product is available on the Python Package Index (PyPI) and conda-forge. | M |
