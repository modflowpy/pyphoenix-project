import networkx as nx
import scipy as sp
import xarray as xr


def test_networkx_to_xarray_over_numpy():
    disu_grid = nx.Graph()
    disu_grid.add_edges_from([(0, 1), (1, 2), (2, 3), (3, 0)])

    # convert the graph to a numpy array, which is dense.
    disu_np = nx.to_numpy_array(disu_grid)
    disu_xr = xr.DataArray(disu_np, dims=("from_node", "to_node"))

    assert disu_xr.shape == (4, 4)

    disu_grid_rebuilt = nx.from_numpy_array(disu_xr.to_numpy())

    assert disu_grid_rebuilt.nodes == disu_grid.nodes
    assert disu_grid_rebuilt.edges == disu_grid.edges


def test_networkx_to_xarray_over_scipy():
    disu_grid = nx.Graph()
    disu_grid.add_edges_from([(0, 1), (1, 2), (2, 3), (3, 0)])

    # convert the graph to a scipy sparse array.
    disu_scipy = nx.to_scipy_sparse_array(disu_grid)
    disu_xr_sparse = xr.Dataset(
        {
            "data": xr.DataArray(disu_scipy.data, dims=("data")),
            "indices": xr.DataArray(disu_scipy.indices, dims=("index")),
            "indptr": xr.DataArray(disu_scipy.indptr, dims=("indptr")),
        }
    )

    assert disu_xr_sparse.data.shape == (8,)

    disu_scipy_rebuilt = sp.sparse.csr_matrix(
        (disu_xr_sparse.data, disu_xr_sparse.indices, disu_xr_sparse.indptr)
    )
    disu_grid_rebuilt = nx.from_scipy_sparse_array(disu_scipy_rebuilt)

    assert disu_grid_rebuilt.nodes == disu_grid.nodes
    assert disu_grid_rebuilt.edges == disu_grid.edges
