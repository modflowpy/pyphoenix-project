from typing import Optional

import numpy as np
import numpy.typing as npt
import pytest

from flopy4.mf6.gwf import Gwf
from flopy4.mf6.spec import blocks, blocks_dict


def test_blocks():
    block_spec = blocks(Gwf)
    options = block_spec[0]
    assert options[-1].name == "netcdf_input_file"


def test_blocks_dict():
    block_spec = blocks_dict(Gwf)
    options = block_spec["options"]
    assert "save_flows" in options


@pytest.mark.parametrize(
    "annotation",
    [
        npt.NDArray[np.float64],  # a type alias on numpy >= 2.5
        np.ndarray[tuple[int, ...], np.dtype[np.float64]],  # numpy < 2.5 form
    ],
)
def test_ndarray_annotation_forms(annotation):
    """Both NDArray annotation forms resolve to their scalar and leaf type."""
    from flopy4.mf6.adapters import _resolve_leaf_type
    from flopy4.mf6.spec import ndarray_scalar

    assert ndarray_scalar(annotation) is np.float64
    assert ndarray_scalar(Optional[annotation]) is None
    assert _resolve_leaf_type(Optional[annotation]) is np.ndarray
