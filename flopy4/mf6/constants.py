import numpy as np

MF6 = "mf6"
FILL_DEFAULT = np.nan
FILL_DNODATA = np.float64(3e30)  # MF6 DNODATA constant
FILL_INT32 = np.int32(-2147483647)  # netcdf-fortran NF90_FILL_INT
FILL_INT64 = np.int64(-2147483647)  # netcdf-fortran NF90_FILL_INT
FILL_FLOAT64 = np.float64(9.96920996838687e36)  # netcdf-fortran NF90_FILL_DOUBLE
LENBOUNDNAME = 40
