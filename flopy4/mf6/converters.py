import types
from typing import Union, get_args, get_origin

import numpy as np
from numpy.typing import NDArray
from xattree import _get_xatspec

from flopy4.mf6.constants import FILL_DNODATA


def convert_array(value, self_, field):
    if not isinstance(value, dict):
        # if not a dict, assume it's a numpy array
        # and let xarray deal with it if it isn't
        return value

    # get spec
    spec = _get_xatspec(type(self_))
    field = spec.arrays[field.name]
    if not field.dims:
        raise ValueError(f"Field {field} missing dims")

    # resolve dims
    explicit_dims = self_.__dict__.get("dims", {})
    inherited_dims = self_.parent.data.dims if self_.parent else {}
    dims = inherited_dims | explicit_dims
    shape = [dims.get(d, d) for d in field.dims]
    unresolved = [d for d in shape if isinstance(d, str)]
    if any(unresolved):
        raise ValueError(f"Couldn't resolve dims: {unresolved}")

    # extract dtype
    origin = get_origin(field.type)
    args = get_args(field.type)
    if origin in (Union, types.UnionType) and args[-1] is types.NoneType:
        origin = args[0]  # Optional
    if origin is NDArray:
        dtype = args[1]
    elif origin is np.ndarray:
        dtype = args[0]
    else:
        raise ValueError(f"Expected NDArray, got {origin}")

    # create array
    a = np.full(shape, fill_value=FILL_DNODATA, dtype=dtype)

    def _get_nn(cellid):
        match len(cellid):
            case 1:
                return cellid[0]
            case 2:
                k, j = cellid
                return k * dims["ncpl"] + j
            case 3:
                k, i, j = cellid
                return k * dims["row"] * dims["col"] + i * dims["col"] + j
            case _:
                raise ValueError(f"Invalid cellid: {cellid}")

    # populate array. TODO: is there a way to do this
    # without hardcoding awareness of kper and cellid?
    if "kper" in dims:
        for kper, period in value.items():
            if kper == "*":
                kper = 0
            match len(shape):
                case 1:
                    a[kper] = v
                case _:
                    for cellid, v in period.items():
                        nn = _get_nn(cellid)
                        a[kper, nn] = v
            if kper == "*":
                break
    else:
        for cellid, v in value.items():
            nn = _get_nn(cellid)
            a[kper, nn] = v

    return a
