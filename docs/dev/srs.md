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

### Intended audience

Hydrologic scientists, engineers, and students that are familiar with the
Python ecosystem and MODFLOW. Another key audience is MODFLOW developers.

The product should be available on major operating systems and hardware
ranging from laptops to HPC systems. The product should be available in
any CPython environment.

**Use cases**

* A hydrologist needs to determine an optimal pumping rate for a well field...

* A professor is teaching a groundwater modeling class...

* A MODFLOW developer is debugging an issue in the UZF package and wants to create a complicated test with many cells and stress periods.

* A MODFLOW developer is setting up worked example to demonstrate how to use a new feature...

### Value proposition

The product will allow defining reproducible, versionable Python workflows
for MODFLOW modeling applications. The product will wrap MODFLOW and other
programs and provide a Pythonic interface to their functionality and input
and output files. FloPy will also be used for MODFLOW development, to test
existing and new functionality.

### Project scope

FloPy 4 will have the same basic responsibilities as FloPy 3:

1. running simulations
2. working with input and output

**Running simulations**

The product will be able to run MODFLOW 6 (and other programs). The product
will be able to load input datasets into MODFLOW 6 (and other programs) by
way of an input specification provided for the program.

**Input and output**

The product must be able to 1) load, modify, and write simulation inputs
and 2) load simulation outputs in several formats, to include any custom
format used by a specific program, as well as standards supported by 3rd
party software.

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
