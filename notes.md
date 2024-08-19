# Development notes

This project aims to reimplement MF6 support for flopy.

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Goals](#goals)
- [Patterns](#patterns)
- [Ideas](#ideas)
- [Questions](#questions)
- [Design](#design)
  - [Data access layer](#data-access-layer)
    - [`MFParam`](#mfparam)
    - [`MFScalar`](#mfscalar)
    - [`MFCompound`](#mfcompound)
    - [`MFArray`](#mfarray)
    - [`MFList`](#mflist)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->


## Goals

- existing `flopy.mf6` functionality intact
- easy for developers to read and debug
- fast read/write routines
- minimal code and maintenance burden
- Pythonic user-facing APIs

## Patterns

- inversion of control
  - core object model should not need to know about the MF6 input format, or any other format
  - NOTE: initial draft combines the access layer and the object model, need to separate them
- autogenerate object model from MF6 IO specification (minimize development/maintenance burden)
- metaclass magic for object model: inspect class attributes, collect specification, attach it as an attribute
- object model classes can emulate builtin containers
  - e.g. implement `UserDict` for:
    - block as mapping of parameters
    - model/package as mapping of blocks
    - simulation as mapping of models/packages
- mixins for cross-cutting concerns (e.g. plotting, exporting)
- signals to propagate data updates throughout simulation/model/package context
  - e.g. if DIS changes, invalidate package properties that assumed prior shape
- data access layer interoperable with appropriate builtin or 3rd-party classes
  - array: mixin implementing NumPy ufuncs etc
  - list: act like `DataFrame`
- convenient string representations
  - `__str__`  of object model **classes** as human-readable (possibly condensed) specification
  - `__repr__` of object model **classes** as exact specification
  - `__str__` of object model **instances** as human-readable (possibly condensed) contents
  - `__repr__` of object model **instances** as full, complete contents

## Ideas

- defer MF6 component generation until install time? 
  - no need to version DFNs and generated files or decide when to sync them from MF6
  - could ship latest MF6 IO spec (DFNs, TOML or otherwise) with each flopy release
  - at first install time, flopy could use prepackaged spec to generate components
  - users could subsequently regenerate components from other versions of the spec
  - new command just to retrieve latest DFNs: `get_spec`? 
  - `generate_classes` no longer retrieves DFNs, just generates code
  - new command `migrate` = `get_spec` + `generate_classes`?

## Questions

- if parameters are defined as class attributes, how to handle parameters whose name overlaps with a python keyword? e.g. `continue`
  - use `attrs`?
      - parameter member names use single leading underscore
      - try `setattr` for unmodified parameter name
          - catch failure due to keyword overlap
          - emit warning
      - unmodified name still accessible via dict

## Design

### Data access layer

#### `MFParam`

todo

#### `MFScalar`

todo

#### `MFCompound`

todo

#### `MFArray`

- Array data handling class.
- Handle 1d, 2d, and 3d arrays natively
- Store array data as flat data until
  - write
  - return to user
- **Attributes and methods**
  - `.value`
    - returns a copy of the reshaped array to user
  - `__getitem__`
    - allow user to get slices of the array data
  - `__setitem__`
    - allow user to set/update slices of the array data'
  - `__str__`
    - print the string representation of the data how it will be written to file (e.g., "CONSTANT 10", "OPEN/CLOSE myhkarray.txt")
  - `.how`
    - return a value that describes how the data is written
  - `.shape`
    - return the required shape of the data
  - `.factor`
    - return the scale factor value
  - `.control_record`
    - return a copy of the control record
  - `get_data()`
    - get a copy the reshaped data
  - `set_data()`
    - method to set new data/update the data
  - `.plot()`
    - plot the data
  - `.export()`
    - export the data
  - `.load()`
    - load the data from file
  - `.plottable`
    - if the data is attached to a model(grid), it is plottable
  - `to_list`
    - converts underlying data type to list
  - `to_numpy`
    - converts underlying data type to *
  - `to_xarray`
  - matching from_*
     
#### `MFList`

- Tabular input data (ex. WEL stress period data)
- Handles reading, setting dtype(s), dtype expansion for boundnames, auxvars
- Must be able to read and set a stress period data block from an advanced packages in an efficient manner
- **Attributes and methods**
  - `.value`
    - returns a copy/view(?) of the underlying recarray or dataframe to the user, should this have a getter/setter property method?
  - `__getitem__`
    - x
  - `__setitem__`
    - x
  - `__getattr__`
    - x
  - `__setattr__`
    - x
  - `__str__`
    - print the recarray to console
  - `.how`
    - return a value that describes how the data is written
  - `.control_record`
    - return a copy of the control record
  - `get_data()`
    - get a copy of the data
  - `set_data()`
    - method to set new/update the data
  - `.plot()`
    - plot the data
  - `.export()`
    - export the data
  - `.load()`
    - load the data from file
  - `.plottable`
    - if the data is attached to a model(grid), it is plottable
  - `.dtype`
    - returns the data type [(name_0, type),...(name_n, type)]
  - `.get_empty_xxxx()`
    - method to get an empty dataframe or recarray
  - `.load()`
    - method to load the data
  - `to_list`
    - converts to list
  - `to_dict`
    - converts to dict
  - `to_records`
    - converts to recarray or dataframe 
  - matching from_"dtype" methods

