import numpy as np

MF6 = "mf6"
FILL_DEFAULT = np.nan
FILL_DNODATA = np.float64(3e30)  # MF6 DNODATA constant
FILL_INT32 = np.int32(-2147483647)  # netcdf-fortran NF90_FILL_INT
FILL_INT64 = np.int64(-2147483647)  # netcdf-fortran NF90_FILL_INT
FILL_FLOAT64 = np.float64(9.96920996838687e36)  # netcdf-fortran NF90_FILL_DOUBLE
LENBOUNDNAME = 40

# A grid's (size, dim) pairs by cellid width: dims named for the grid's
# axes, DIS's (layer, row, col), DISV's (layer, cell), and DISU's (node,).
GRID_DIMS: dict[int, tuple[tuple[str, str], ...]] = {
    3: (("nlay", "layer"), ("nrow", "row"), ("ncol", "col")),
    2: (("nlay", "layer"), ("ncpl", "cell")),
    1: (("nodes", "node"),),
}
