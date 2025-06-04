from typing import Any, Tuple

import numpy as np
import sparse
import xattree
from numpy.typing import NDArray
from xarray import DataArray
from xattree import get_xatspec

from flopy4.mf6.component import Component
from flopy4.mf6.config import SPARSE_THRESHOLD
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.spec import get_blocks


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

    def _get_nn(cellid):
        match len(cellid):
            case 1:
                return cellid[0]
            case 2:
                k, j = cellid
                return k * dims["ncpl"] + j
            case 3:
                k, i, j = cellid
                return k * dims["nrow"] * dims["ncol"] + i * dims["ncol"] + j
            case _:
                raise ValueError(f"Invalid cellid: {cellid}")

    # populate array. TODO: is there a way to do this
    # without hardcoding awareness of kper and cellid?
    if "nper" in dims:
        for kper, period in value.items():
            if kper == "*":
                kper = 0
            match len(shape):
                case 1:
                    set_(a, period, kper)
                    # a[(kper,)] = period
                case _:
                    for cellid, v in period.items():
                        nn = _get_nn(cellid)
                        set_(a, v, kper, nn)
                        # a[(kper, nn)] = v
            if kper == "*":
                break
    else:
        for cellid, v in value.items():
            nn = _get_nn(cellid)
            set_(a, v, nn)
            # a[(nn,)] = v

    return final(a)


def unstructure_array(value: DataArray) -> dict:
    """
    Convert a dense numpy array or a sparse COO array to a sparse
    dictionary representation suitable for serialization into the
    MF6 list-based input format.
    """
    # make sure dim 'kper' is present
    time_dim = "nper"
    if time_dim not in value.dims:
        raise ValueError(f"Array must have dimension '{time_dim}'")

    if isinstance(value.data, sparse.COO):
        coords = value.coords
        data = value.data
    else:
        coords = np.array(np.nonzero(value.data)).T  # type: ignore
        data = value.data[tuple(coords.T)]  # type: ignore
    if not coords.size:  # type: ignore
        return {}
    match value.ndim:
        case 1:
            return {int(k): v for k, v in zip(coords[:, 0], data)}  # type: ignore
        case 2:
            return {(int(k), int(j)): v for (k, j), v in zip(coords, data)}  # type: ignore
        case 3:
            return {(int(k), int(i), int(j)): v for (k, i, j), v in zip(coords, data)}  # type: ignore
    return {}


def unstructure_component(value: Component) -> dict[str, Any]:
    data = xattree.asdict(value)
    for block in get_blocks(value.dfn).values():
        for field_name, field in block.items():
            # unstructure arrays destined for list-based input
            if field["type"] == "recarray" and field["reader"] != "readarray":
                data[field_name] = unstructure_array(data[field_name])
    return data


def unstructure_oc(value: Any) -> dict[str, Any]:
    data = xattree.asdict(value)
    for block_name, block in get_blocks(value.dfn).items():
        if block_name == "period":
            # Dynamically collect all recarray fields in perioddata block
            array_fields = []
            for field_name, field in block.items():
                # Try to split field_name into action and kind, e.g. save_head -> ("save", "head")
                action, rtype = field_name.split("_")
                array_fields.append((action, rtype, field_name))

            # Unstructure all arrays and collect all unique periods
            arrays = {}
            all_periods = set()  # type: ignore
            for action, rtype, field_name in array_fields:
                arr = unstructure_array(data.get(field_name, {}))
                arrays[(action, rtype)] = arr
                if isinstance(arr, dict):
                    all_periods.update(arr.keys())
            all_periods = sorted(all_periods)  # type: ignore

            perioddata = {}  # type: ignore
            for kper in all_periods:
                for (action, rtype), arr in arrays.items():
                    if kper in arr:
                        if kper not in perioddata:
                            perioddata[kper] = []
                        perioddata[kper].append((action, rtype, arr[kper]))

            data["period"] = perioddata
        else:
            for field_name, field in block.items():
                # unstructure arrays destined for list-based input
                if field["type"] == "recarray" and field["reader"] != "readarray":
                    data[field_name] = unstructure_array(data[field_name])
    return data
