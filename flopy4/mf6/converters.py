from typing import Any, Tuple

import numpy as np
import sparse
from numpy.typing import NDArray
from xattree import get_xatspec

from flopy4.mf6.config import SPARSE_THRESHOLD
from flopy4.mf6.constants import FILL_DNODATA


def convert_array(value, self_, field) -> NDArray:
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
