# Requirements for the pyphoenix-project
The pyphoenix-project is a development project to migrate from the existing
implementation of mf6 for flopy: 

The code should maintain the existing functionality of flopy.mf6, provide
fast read/write routines, and be easy to read and debug from the developer's 
standpoint.

### Low level objects/data model

#### `MFArray()`
   - Array data handling class.
   - Handle 1d, 2d, and 3d arrays natively
   - Store array data as flat data until
     - write
     - return to user
   - **Required attributes and methods**
     - `.array` (should this be changed to `.values`?)
       - returns a copy of the reshaped array to user
     - `__getitem__`
       - allow user to get slices of the array data
     - `__setitem__`
       - allow user to set/update slices of the array data'
     - `__str__`
       - print the string representation of the data how it will be written
to file (e.g., "CONSTANT 10", "OPEN/CLOSE myhkarray.txt")
     - `.how`
       - return a value that describes how the data is written
     - `path`
       - file path of data
     - `block`
       - data block name
     - `name`
       - variable name
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
     
#### `MFList()`
   - Tabular input data (ex. WEL stress period data)
   - Handles reading, setting dtype(s), dtype expansion for boundnames, 
auxvars
   - Must be able to read and set a stress period data block from an advanced
packages in an efficient manner
   - **Required attributes and methods**
     - `.array` (should this be changed to `.values`?)
       - returns a copy/view(?) of the underlying recarray or dataframe to the 
user, should this have a getter/setter property method?
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
     - `path`
       - file path of data
     - `block`
       - data block name
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
     - `.dataframe/.recarray`
       - depends on the underlying data type but provide a conversion to the 
other. should this have a getter/setter property method?
     - `.dtype`
       - returns the data type [(name_0, type),...(name_n, type)]
     - `.get_empty_xxxx()`
       - method to get an empty dataframe or recarray
     - `.load()`
       - method to load the data
     - 