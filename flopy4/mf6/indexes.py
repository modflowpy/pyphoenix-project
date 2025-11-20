import pandas as pd
import xarray as xr
from xarray.core.indexes import Index, PandasIndex
from xarray.core.indexing import merge_sel_results


def alias(dataset: xr.Dataset, old_name: str, new_name: str) -> PandasIndex:
    """
    Alias a dimension coordinate to a coordinate with a different name.
    Suggested by Benoit Bovy https://github.com/pydata/xarray/pull/10076#issuecomment-2809041994.
    """
    try:
        size = dataset.sizes[old_name]
    except KeyError:
        size = dataset.attrs[old_name]
    return PandasIndex(pd.RangeIndex(size, name=new_name), dim=old_name)


class MetaIndex(Index):
    """
    Combine multiple indexes into a single index.
    Adapted from https://docs.xarray.dev/en/stable/internals/how-to-create-custom-index.html#meta-indexes.
    """

    def __init__(self, indices):
        self._indices = indices

    @classmethod
    def from_variables(cls, variables):
        return {k: PandasIndex.from_variables({k: v}) for k, v in variables.items()}

    def create_variables(self, variables=None):
        idx_vars = {}
        for index in self._indices.values():
            idx_vars.update(index.create_variables(variables))
        return idx_vars

    def sel(self, labels):
        results = []
        for k, index in self._indices.items():
            if k in labels:
                results.append(index.sel({k: labels[k]}))
        return merge_sel_results(results)


def grid_index(dataset: xr.Dataset) -> MetaIndex:
    return MetaIndex(
        {
            "lay": alias(dataset, "nlay", "lay"),
            "col": alias(dataset, "ncol", "col"),
            "row": alias(dataset, "nrow", "row"),
        }
    )


def time_index(dataset: xr.Dataset) -> PandasIndex:
    return alias(dataset, "nper", "kper")
