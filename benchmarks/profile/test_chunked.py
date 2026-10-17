"""NPF arrays from numpy vs. dask: writing, ``to_xarray`` and loading.

The package is built directly from arrays, with no parsing, so writing
shows the dask streaming path on its own: the writer iterates dask blocks
a layer at a time, never holding the whole array. Sizes: `small`, 500K
nodes (5 x 100 x 1000), and `large`, 10M (20 x 500 x 1000; slow).

- `test_npf_write` -- unstructure and write to text.
- `test_npf_to_xarray` -- ``Npf.to_xarray``.
- `test_npf_load` -- ``Npf.load`` from the text the numpy package wrote.
"""

from types import SimpleNamespace

import numpy as np
import pytest
from _scenario import bench

SIZES = {"small": (5, 100, 1000), "large": (20, 500, 1000)}


@pytest.fixture(scope="module", params=["small", pytest.param("large", marks=pytest.mark.slow)])
def npf(request, tmp_path_factory):
    import dask.array as da

    from flopy4.mf6.codec import dumps
    from flopy4.mf6.converter import COMPONENT_CONVERTER
    from flopy4.mf6.gwf.npf import Npf

    nlay, nrow, ncol = SIZES[request.param]
    nodes, ncpl = nlay * nrow * ncol, nrow * ncol
    dims = {"nlay": nlay, "nrow": nrow, "ncol": ncol, "nodes": nodes, "ncpl": ncpl}
    k = np.random.default_rng(42).uniform(0.001, 100.0, size=nodes)
    k_dask = da.from_array(k.reshape(nlay, ncpl), chunks=(1, ncpl)).reshape(-1)
    icelltype = np.zeros(nodes, dtype=np.int64)
    packages = {
        "numpy": Npf(k=k, icelltype=icelltype, dims=dims),
        "dask": Npf(k=k_dask, icelltype=icelltype, dims=dims),
    }
    path = tmp_path_factory.mktemp("npf") / "synthetic.npf"
    path.write_text(dumps(COMPONENT_CONVERTER.unstructure(packages["numpy"])))
    return SimpleNamespace(size=request.param, dims=dims, packages=packages, path=path)


@pytest.mark.parametrize("backend", ["numpy", "dask"])
def test_npf_write(benchmark, npf, backend):
    from flopy4.mf6.codec import dumps
    from flopy4.mf6.converter import COMPONENT_CONVERTER

    package = npf.packages[backend]
    benchmark.group = f"npf-write[{npf.size}]"
    bench(benchmark, lambda: dumps(COMPONENT_CONVERTER.unstructure(package)))


@pytest.mark.parametrize("backend", ["numpy", "dask"])
def test_npf_to_xarray(benchmark, npf, backend):
    benchmark.group = f"npf-to-xarray[{npf.size}]"
    bench(benchmark, npf.packages[backend].to_xarray)


def test_npf_load(benchmark, npf):
    from flopy4.mf6.gwf.npf import Npf

    benchmark.group = f"npf-load[{npf.size}]"
    benchmark.extra_info["n_bytes"] = npf.path.stat().st_size
    bench(benchmark, lambda: Npf.load(npf.path, dims=npf.dims))
