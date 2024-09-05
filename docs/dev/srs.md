# FloPy 4 software requirement specifications (SRS)

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Introduction](#introduction)
  - [Intended audience](#intended-audience)
  - [Value proposition](#value-proposition)
  - [Project scope](#project-scope)
- [Motivation](#motivation)
  - [Consistency](#consistency)
  - [Maintenance](#maintenance)
  - [Introspection](#introspection)
  - [Performance](#performance)
  - [Invariants](#invariants)
- [Goals](#goals)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## Introduction

This is the Software Requirement Specifications (SRS) document for FloPy 4, also
called *the product* or flopy4.

### Product scope

flopy4 will be a software product to pre- and post-Process MODFLOW-based 
model input and output.

Pre-processing will be limited to preparing model input datasets. 

Post-processing will be limited to reading model output into internal data formats 
that can be used by the product.

For specific use cases, model input and output data will be processed by the 
product into formats that can be analyzed in other libraries.

The product will also be able to run MODFLOW simulations.

The product can load existing model input datasets that were not necessarily 
created by the product but conform to MODFLOW input and output specifications.

flopy4 will replace the MODFLOW 6 targeted capabilities of the current FloPy 3.

flopy4 will also replace the following capabilities of FloPy 3:
  * PEST (?)
  * capability 2 (discuss)

### Product value

The product will allow defining reproducible, versionable Python workflows for
MODFLOW modeling applications. 

The product will wrap MODFLOW and other programs and provide a Pythonic interface 
to their functionality and input and output files. 

flopy4 is essential to the MODFLOW development process for testing existing and 
newly developed functionality.

### Intended audience: 

Hydrologic scientists, engineers, and students who are familiar with the Python 
ecosystem and want to use MODFLOW for their hydrologic applications. The other 
key audience is the team of MODFLOW software developers.

### Intended use: 

The product should be available on the major operating systems 
(Windows, Linux, MacOS) and hardware ranging from laptops to HPC systems.

The product will be used through Python scripts and Jupyter notebooks. 

The product can be relied upon as a core component by other libraries and 
tools that offer more advanced or domain specific or application specific 
functionality.

#### Use cases

* A hydrologist needs to determine an optimal pumping rate for a well field...

* A student wants to simulate salt water intrusion in a coastal aquifer and 
visualize results...

* A professor is teaching a groundwater modeling class...

* A hydrologic institute maintains their own suite of advanced pre- and 
post-processing utilities that can rely on flopy4 as a component for its 
core capabilities...

* A MODFLOW developer is debugging an issue in the UZF package and wants to 
create a complicated test with many cells and stress periods...

* A MODFLOW developer is setting up a worked example to demonstrate how to 
use a new feature...

## System requirements and functional requirements
tbd

## External interface requirements
tbd

## Non-functional requirements (NRFs)
tbd

**Maintainability**

flopy4 should maintain a separation of concerns with respect to hydrology and
software engineering. The hydrologic modeler should not be concerned with the
technical details of flopy4's internal data storage or parallel processing 
implementation, for example, and a software engineer should be able to work 
on the code without detailed knowledge on complex hydrologic concepts.


## Motivation

FloPy 3 supports a wide range of functionality, but presents challenges
in several areas:

- APIs for MF6 and other programs are not consistent
- MF6 module is complicated and difficult to maintain
- `repr` inconsistent, uninformative or not available
- Invalid state due to context-unaware components
- Inadequate performance for very large simulations

### Consistency

The `flopy.mf6` module departs considerably from the older `flopy.modflow`
module. This requires more memorization (or more R'ing TFM) for users and
developers alike, and makes maintenance harder.

Both modules are strongly coupled to the relevant programs' input format.

We would like a consistent core framework for any modeling program, which
can be applied to MODFLOW 6, older MODFLOW programs, and other hydrologic
simulators. The framework should be agnostic to the IO format used by any
particular program.

### Maintenance

The `flopy.mf6` module is large and developers have struggled to maintain
it. Deep abstraction in the object model raises barriers to comprehension
and error messages are not easy to trace back to the offending component.
Debugging is also difficult.

### Introspection

Component classes reproduce their input specification verbatim. This is
redundant and yet not particularly useful or Pythonic; more informative
would be a format-agnostic specification in terms of Python primitives,
containers, and classes, which can be translated into any given format
upon request. This allows flexibility to translate DFN specifications
to a different format, e.g. TOML, YAML or JSON.

Component classes also provide a data access layer via `.get_data()` and
`set_data()` &mdash; it would be simpler just to get/set the attributes
normally and intercept these behind the scenes for any magic necessary.

### Performance

TODO: describe current issues

### Invariants

FloPy 3 has a "check" mechanism for validating simulation configurations,
but this must be run manually by the user, and no straightforward method
for extension is available.

This allows simulations to be initialized in an invalid state, which may
go unnoticed until runtime, producing less than informative errors from
the modeling program.

The most obvious example is that grid dimensions can be changed with no warning to the user, and no attempt to coerce package array data to the
new shape.

We would like automatic enforcement of invariants whenever a simulation
changes.

## Goals

With the above in mind, we want the next version of FloPy to

- preserve existing `flopy.mf6` functionality
- be consistent, user-friendly and Pythonic
- be easy to read, debug, diagnose and test
- be memory-efficient and provide fast IO
- impose a minimal maintenance burden
