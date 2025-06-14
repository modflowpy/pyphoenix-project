from typing import Any, Tuple

import numpy as np
import sparse
import xattree
from numpy.typing import NDArray
from xarray import DataArray
from xattree import get_xatspec

from flopy4.adapters import get_cellid, get_nn
from flopy4.mf6.component import Component
from flopy4.mf6.config import SPARSE_THRESHOLD
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.spec import get_blocks, is_list_field


# TODO: convert to a cattrs structuring hook so we don't have to
# apply separately to all array fields?
def structure_array(value, self_, field) -> NDArray:
    """
    Convert a sparse dictionary representation of an array to a
    dense numpy array or a sparse COO array.
    """

    if not isinstance(value, dict):
        # if not a dict, assume it's a numpy array
        # and let xarray deal with it if it isn't
        return value

    # get spec
    spec = get_xatspec(type(self_))
    field = spec[field.name]
    if not field.dims:
        raise ValueError(f"Field {field} missing dims")

    # resolve dims
    explicit_dims = self_.__dict__.get("dims", {})
    inherited_dims = dict(self_.parent.data.dims) if self_.parent else {}
    dims = inherited_dims | explicit_dims
    shape = [dims.get(d, d) for d in field.dims]
    unresolved = [d for d in shape if isinstance(d, str)]
    if any(unresolved):
        raise ValueError(f"Couldn't resolve dims: {unresolved}")

    if np.prod(shape) > SPARSE_THRESHOLD:
        a: dict[Tuple[Any, ...], Any] = dict()

        def set_(arr, val, *ind):
            arr[tuple(ind)] = val

        def final(arr):
            coords = np.array(list(map(list, zip(*arr.keys()))))
            return sparse.COO(
                coords,
                list(arr.values()),
                shape=shape,
                fill_value=field.default or FILL_DNODATA,
            )
    else:
        a = np.full(shape, FILL_DNODATA, dtype=field.dtype)  # type: ignore

        def set_(arr, val, *ind):
            arr[ind] = val

        def final(arr):
            arr[arr == FILL_DNODATA] = field.default or FILL_DNODATA
            return arr

    # populate array. TODO: is there a way to do this
    # without hardcoding awareness of kper and cellid?
    if "nper" in dims:
        for kper, period in value.items():
            if kper == "*":
                kper = 0
            match len(shape):
                case 1:
                    set_(a, period, kper)
                case _:
                    for cellid, v in period.items():
                        nn = get_nn(cellid, **dims)
                        set_(a, v, kper, nn)
            if kper == "*":
                break
    else:
        for cellid, v in value.items():
            nn = get_nn(cellid, **dims)
            set_(a, v, nn)
    return final(a)


def unstructure_array(value: DataArray) -> dict:
    """
    Convert a dense numpy array or a sparse COO array to a sparse
    dictionary representation suitable for serialization into the
    MF6 list-based input format.

    The input array must have a time dimension named 'nper', i.e.
    it must be stress period data for some MODFLOW 6 component.

    Returns:
        dict: {kper: {spatial indices: value, ...}, ...}
    """
    if (time_dim := "nper") not in value.dims:
        raise ValueError(f"Array must have dimension '{time_dim}'")
    if isinstance(value.data, sparse.COO):
        coords = value.coords
        data = value.data
    else:
        coords = np.array(np.where(value.data != FILL_DNODATA)).T  # type: ignore
        data = value.data[tuple(coords.T)]  # type: ignore
    if not coords.size:  # type: ignore
        return {}
    result = {}
    match value.ndim:
        case 1:
            # Only kper, no spatial dims
            for kper, v in zip(coords[:, 0], data):
                result[int(kper)] = v
        case _:
            # kper + spatial dims
            for row, v in zip(coords, data):
                kper = int(row[0])  # type: ignore
                spatial = tuple(int(x) for x in row[1:])  # type: ignore
                if kper not in result:
                    result[kper] = {}
                # flatten spatial index if only one spatial dim
                key = spatial[0] if len(spatial) == 1 else spatial
                result[kper][key] = v
    return result


def unstructure_component(value: Component) -> dict[str, Any]:
    data = xattree.asdict(value)
    blocks = get_blocks(value.dfn)
    for block in blocks.values():
        for field_name, field in block.items():
            if is_list_field(field):
                data[field_name] = unstructure_array(data[field_name])
    return data


def unstructure_tdis(value: Any) -> dict[str, Any]:
    data = xattree.asdict(value)
    blocks = get_blocks(value.dfn)
    for block_name, block in blocks.items():
        if block_name == "perioddata":
            arrs_d = {}
            periods = set()  # type: ignore
            for field_name in block.keys():
                arr = data.get(field_name, None)
                arr_d = {} if arr is None else unstructure_array(arr)
                arrs_d[field_name] = arr_d
                periods.update(arr_d.keys())
            periods = sorted(periods)  # type: ignore
            perioddata = {}  # type: ignore
            for kper in periods:
                line = []
                if kper not in perioddata:
                    perioddata[kper] = []  # type: ignore
                for arr_d in arrs_d.values():
                    if val := arr_d.get(kper, None):
                        line.append(val)
                perioddata[kper] = tuple(line)
            data["perioddata"] = perioddata
    return data


def unstructure_chd(value: Any) -> dict[str, Any]:
    if (parent := value.parent) is None:
        raise ValueError(
            "CHD cannot be unstructured without a parent "
            "model and corresponding grid discretization."
        )
    grid = parent.grid
    data = xattree.asdict(value)
    blocks = get_blocks(value.dfn)
    for block_name, block in blocks.items():
        if block_name == "period":
            arrs_d = {}
            periods = set()  # type: ignore
            for field_name in block.keys():
                arr = data.get(field_name, None)
                arr_d = {} if arr is None else unstructure_array(arr)
                arrs_d[field_name] = arr_d
                periods.update(arr_d.keys())
            periods = sorted(periods)  # type: ignore
            perioddata = {}  # type: ignore
            for kper in periods:
                line = []
                if kper not in perioddata:
                    perioddata[kper] = []  # type: ignore
                for arr_d in arrs_d.values():
                    if val := arr_d.get(kper, None):
                        for nn, v in val.items():
                            cellid = get_cellid(nn, grid)
                            line.append((*cellid, v))
                perioddata[kper] = tuple(line)
            data["period"] = perioddata
    return data


def unstructure_oc(value: Any) -> dict[str, Any]:
    data = xattree.asdict(value)
    blocks = get_blocks(value.dfn)
    for block_name, block in blocks.items():
        if block_name == "period":
            fields = []
            for field_name, field in block.items():
                action, rtype = field_name.split("_")
                fields.append((action, rtype, field_name))
            arrs_d = {}
            periods = set()  # type: ignore
            for action, rtype, field_name in fields:
                arr = data.get(field_name, None)
                arr_d = {} if arr is None else unstructure_array(arr)
                arrs_d[(action, rtype)] = arr_d
                periods.update(arr_d.keys())
            periods = sorted(periods)  # type: ignore
            perioddata = {}  # type: ignore
            for kper in periods:
                if kper not in perioddata:
                    perioddata[kper] = []
                for (action, rtype), arr_d in arrs_d.items():
                    if arr := arr_d.get(kper, None):
                        perioddata[kper].append((action, rtype, arr))
            data["period"] = perioddata
        else:
            for field_name, field in block.items():
                if is_list_field(field):
                    data[field_name] = unstructure_array(data[field_name])
    return data
