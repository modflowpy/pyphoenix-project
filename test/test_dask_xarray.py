import numpy as np
import xarray as xr

# These tests show how we could use a chunked and lazy dask array
# to read a netcdf file.
# In this case we want to write the data to a single file,
# so we need to ensure that the data is sequential and in the right order.
# We can't use xr.map_blocks, because it is a parallel operation.
# Instead we need to loop over the blocks and compute them one by one. (test 2)


def test_netcdf_with_map_blocks(tmp_path):
    data = xr.DataArray(range(1, 1_000), dims=("x",))
    nc_path = tmp_path / "test_netcdf_with_map_blocks.nc"
    data.to_netcdf(nc_path)
    data.close()
    data = xr.open_dataarray(nc_path, chunks={"x": 100})

    output_file = []

    # Option 1: this works, but all blocks are still loaded into memory.
    # That's because we need to return the block.
    # And that data is then collected and returned by compute().
    # Even if we don't use it.
    # And because it's going in parallel, we don't have control of the order.
    def append_to_output_file(block):
        output_file.append(block.data)
        return block

    result = data.map_blocks(
        append_to_output_file,
        template=data,
    )

    result.compute()
    assert len(output_file) == 10


def test_netcdf_with_dask_map_blocks(tmp_path):
    data = xr.DataArray(range(1, 1_000), dims=("x",))
    nc_path = tmp_path / "test_netcdf_with_dask_map_blocks.nc"
    data.to_netcdf(nc_path)
    data.close()
    data = xr.open_dataarray(nc_path, chunks={"x": 100})

    output_file = []

    # Option 2 is easier.
    # We simply loop over the raw dask blocks and compute them one by one.
    for block in data.data.blocks:
        block_data = block.compute()
        output_file.append(block_data)

    assert len(output_file) == 10
    assert np.all(np.equal(output_file[0], range(1, 101)))
