# FloPy 4 software requirement specifications (SRS)

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [FloPy 4 software requirement specifications (SRS)](#flopy-4-software-requirement-specifications-srs)
  - [Introduction](#introduction)
    - [Product scope](#product-scope)
    - [Product value](#product-value)
    - [Intended audience](#intended-audience)
    - [Intended use](#intended-use)
    - [Use cases](#use-cases)
  - [Motivation](#motivation)
    - [Consistency](#consistency)
    - [Maintenance](#maintenance)
    - [Introspection](#introspection)
    - [Performance](#performance)
    - [Invariants](#invariants)
    - [Maintainability](#maintainability)
  - [Goals](#goals)
  - [System requirements and functional requirements](#system-requirements-and-functional-requirements)
    - [Functional requirements](#functional-requirements)
    - [External interface requirements](#external-interface-requirements)
    - [Non-functional requirements](#non-functional-requirements)
    - [System requirements](#system-requirements)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## Introduction

This is the Software Requirement Specifications (SRS) document for FloPy 4, also
called *the product* or flopy4.

### Product scope

flopy4 will be a software product to pre- and post-process MODFLOW-based model input and output.
Pre-processing will be limited to preparing model input datasets, mesh generation, and model input manipulation capabilities.
Post-processing will be limited to reading model output into internal data formats that can be used by the product, plotting utilities, and rudimentary analysis capabilities.
For specific use cases, model input and output data will be processed by the product into formats that can be analyzed in other libraries.

The product will be able to run MODFLOW simulations.

The product can load existing model input datasets that were not necessarily created by the product, but conform to MODFLOW input and output specifications.

flopy4 will replace the MODFLOW 6 targeted capabilities of the current FloPy 3 library.

### Product value

The product will allow defining reproducible, versionable Python workflows for
MODFLOW modeling applications.

The product will wrap MODFLOW and other programs and provide a Pythonic interface to their functionality and input and output files.

flopy4 is essential to the MODFLOW development process for testing existing and newly developed functionality.

flopy4 will be compatible with the definition files (DFNs) that come with MODFLOW 6, and will thus always be up-to-date with the latest MODFLOW 6 capabilities.

### Intended audience

Hydrologic scientists, engineers, and students who are familiar with the Python ecosystem and want to use MODFLOW for their hydrologic applications.
The other key audience is the team of MODFLOW software developers.

### Intended use

The product should be available on the major operating systems (Windows, Linux, MacOS) and hardware ranging from laptops to HPC systems.
The product will be used through Python scripts, Jupyter notebooks, pytest, and ipython.

The product can be relied upon as a core component by other libraries and tools that offer more advanced, domain specific, or application specific functionality.

### Use cases

- A hydrologist needs to determine an optimal pumping rate for a well field...

- A student wants to simulate salt water intrusion in a coastal aquifer and visualize results...

- A professor is teaching a groundwater modeling class...

- A hydrologic institute maintains their own suite of advanced pre- and post-processing utilities that can rely on flopy4 as a component for its core capabilities...

- A MODFLOW developer is debugging an issue in the UZF package and wants to create a complicated test with many cells and stress periods...

- A MODFLOW developer is setting up a worked example to demonstrate how to use a new feature...

## Motivation

FloPy 3 supports a wide range of functionality, but presents challenges
in several areas:

- APIs for MF6 and other programs are not consistent
- MF6 module is complicated and difficult to maintain
- `repr` inconsistent, uninformative or not available
- Invalid state due to context-unaware components
- Inadequate performance for very large simulations

### Consistency

The `flopy.mf6` module departs considerably from the older `flopy.modflow` module.
This requires more memorization (or more R'ing TFM) for users and developers alike, and makes maintenance harder.
Both modules are strongly coupled to the relevant programs' input format.

We would like a consistent core framework for any modeling program, which can be applied to MODFLOW 6, older MODFLOW programs, and other hydrologic simulators.
The framework should be agnostic to the IO format used by any particular program.

### Maintenance

The `flopy.mf6` module is large and developers have struggled to maintain it.
Deep abstraction in the object model raises barriers to comprehension and error messages are not easy to trace back to the offending component.
Debugging is also difficult.

### Introspection

Component classes reproduce their input specification verbatim.
This is redundant and yet not particularly useful or pythonic;
more informative would be a format-agnostic specification in terms of Python primitives, containers, and classes, which can be translated into any given format upon request.
This allows flexibility to translate DFN specifications to a different format, e.g. TOML, YAML or JSON.

Component classes also provide a data access layer via `.get_data()` and `set_data()` &mdash; it would be simpler just to get/set the attributes normally and intercept these behind the scenes for any magic necessary.

### Performance

TODO: describe current issues

### Invariants

FloPy 3 has a "check" mechanism for validating simulation configurations, but this must be run manually by the user, and no straightforward method for extension is available.
This allows simulations to be initialized in an invalid state, which may go unnoticed until runtime, producing less than informative errors from the modeling program.
The most obvious example is that grid dimensions can be changed with no warning to the user, and no attempt to coerce package array data to the new shape.
We would like automatic enforcement of invariants whenever a simulation changes.

### Maintainability

flopy4 should maintain a separation of concerns with respect to hydrology and software engineering.
The hydrologic modeler should not be concerned with the technical details of flopy4's internal data storage or parallel processing implementation,
for example, and a software engineer should be able to work on the code without detailed knowledge on complex hydrologic concepts.

## Goals

With the above in mind, we want the next version of FloPy to:

- preserve existing `flopy.mf6` functionality
- be consistent, user-friendly and pythonic
- be easy to read, debug, diagnose and test
- be memory-efficient and provide fast IO
- impose a minimal maintenance burden

## System requirements and functional requirements

The requirements below are written up through interviews with stakeholders and internal research of the flopy code base.

The requirements are categorized through the [MoSCoW method](https://en.wikipedia.org/wiki/MoSCoW_method), prioritizing which requirements Must, Should, Could, and Won't go into the first iteration of the flopy 4 project.

### Functional requirements

| ID      | Description | MoSCoW |
| ------- | ----------- | ------ |
| FUNC-1  | flopy4 must be able to read and write MODFLOW 6 input files and read MODFLOW 6 output files. | M |
| FUNC-2  | flopy4 must be able to run MODFLOW 6 simulations and report back on the run status. | M |
| FUNC-3  | flopy4 must work with multiple versions of MODFLOW 6, based on the DFN files. And it must support all packages that come with that version of MODFLOW 6. | M |
| FUNC-4  | The product lets the user define a model domain, including grid dimensions, cell sizes, and boundary conditions. | M |
| FUNC-5  | flopy4 can create grid definitions in different formats: structured (DIS), vertex (DISV), unstructured (DISU). And is open for expansion of new grid definitions. | M |
| FUNC-6  | flopy4 can create MODFLOW models that support parallel processing. It can pre-process models by splitting them up, ready for parallel computation. | M |
| FUNC-7  | The product contains functions to plot model output and gives the user configurable or extendable options for customization. | M |
| FUNC-8  | The product contains functions to plot model input and gives the user configurable or extendable options for customization. | M |
| FUNC-9  | The product can export its internal data model to different types of file formats, such as NetCDF, VTK, and geospatial standards. | M |
| FUNC-10  | Extensive and optional validation on the final input model can be used to ensure that the model is free from detectable errors and to warn the user of potential errors before running the simulation. | S |
| FUNC-11 | The validation can be extended by the user to include custom checks. | C |
| FUNC-12 | Instantiation of packages and models should work in an intuitive way that does not depend on the specific order of function calls. E.g., packages can be created without creating a simulation or model first. | M |
| FUNC-13 | Functionality is in place to set up example simulations with predefined setup combinations of models and packages already configured. | C |
| FUNC-14 | Flopy is a non-intrusive package when it comes to reading, writing, and running the model. When writing out a model that was read, the simulation output must give the exact same results. | C |

### External interface requirements

| ID      | Description | MoSCoW |
| ------- | ----------- | ------ |
| API-1   | flopy4 should give the opportunity for external libraries to extend its capabilities by providing a plugin system. This can be useful for new plotting mechanisms, file export formats, or custom input file formats that can be converted to MODFLOW data. | C |
| API-2   | New DFN files are compatible with flopy4, and the product should be able to generate a definition of the packages that are applicable to that version of MODFLOW 6. | M |
| API-3   | The product strives for a consistency in its public API between MODFLOW 6 and older MODFLOW packages. | S |
| API-4   | The product has programmatic access to example models, to make it quick for the user to run an example model, or to alter the examples to their liking. | C |
| API-5   | Input parameters have clear units to avoid confusion. E.g., using SI units only, or by providing usage of a python units package. | C |
| API-6   | The product has a unified understanding of date and time. | M |
| API-7   | The user is aided in their development process by providing python type hints directly from the API with accompanying documentation on all the input parameters. | M |

### Non-functional requirements

| ID      | Description | MoSCoW |
| ------- | ----------- | ------ |
| NFR-1   | The product must be able to create large models that are larger than the available memory on the user's machine. | M |
| NFR-2   | The product should be able to create an example model of the United States with a **?1 km?** grid resolution. | ? |
| NFR-3   | Clear and informative error messages should be provided to the user when an error occurs, also during model input validation. | M |
| NFR-4   | The user documentation makes a clear distinction in user public and internal API. | M |
| NFR-5   | The user documentation provides a complete overview of the definition file specification. | M |

### System requirements

| ID      | Description | MoSCoW |
| ------- | ----------- | ------ |
| SYS-1   | flopy4 must be able to run within a python environment supporting versions that comply with scientific-python.org guidelines: <https://scientific-python.org/specs/spec-0000/>. This is due to its dependency on the Numpy, Matplotlib, and XArray libraries, and flopy4 should not be conflicting with user installed libraries. | M |
| SYS-2   | The product must be able to run on the following operating systems: Windows, Linux, MacOS. | M |
| SYS-3   | The product must be distributed via the Python Package Index (PyPI) and be installable via pip. Additionally, the product must be installable via conda-forge. | M |
