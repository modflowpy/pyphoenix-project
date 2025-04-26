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
        return {
            k: PandasIndex.from_variables({k: v}) for k, v in variables.items()
        }

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

    def to_pandas_index(self) -> pd.Index:
        # from https://github.com/corteva/rioxarray/pull/846/files#diff-917105823f61e63ef4afde8bed408a6c249e375690e56bc800406676f02551d8R418
        if len(self._indices) == 1:
            index = next(iter(self._indices.values()))
            if isinstance(index, PandasIndex):
                return index.to_pandas_index()

        raise ValueError("Cannot convert MetaIndex to pandas.Index")


def grid_index(dataset: xr.Dataset) -> MetaIndex:
    return MetaIndex(
        {
            # TODO add 'per' (stress period)
            "lay": alias(dataset, "nlay", "lay"),
            "col": alias(dataset, "ncol", "col"),
            "row": alias(dataset, "nrow", "row"),
            # "node": alias(dataset, "nnodes", "node"),
            # TODO: adding node breaks the other three.
            # and just having node by itself works. why?
        }
    )


def time_index(dataset: xr.Dataset) -> PandasIndex:
    return alias(dataset, "nper", "per")
