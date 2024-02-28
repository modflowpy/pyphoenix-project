# Requirements for the pyphoenix-project
The pyphoenix-project is a development project to migrate from the existing
implementation of mf6 for flopy: 

The code should maintain the existing functionality of flopy.mf6, provide
fast read/write routines, and be easy to read and debug from the developer's 
standpoint.

### Low level objects/data model

#### MFArray()
   - Array data handling class.
   - Handle 1d, 2d, and 3d arrays natively
   - Store array data as flat data until
     - write
     - return to user
   - **Required attributes and methods**
     - `.array`
       - returns a copy of the reshaped array to user
     - `__getitem__`
       - allow user to get slices of the array data
     - `__setitem__`
       - allow user to set/update slices of the array data'
     - `.how`
       - return a value that describes how the data is written
     - `.shape`
       - return the required shape of the data
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
       - if the data is attached to a model, it is plottable