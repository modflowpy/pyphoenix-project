from typing import ClassVar, Optional

import attrs
import numpy as np
from numpy.typing import NDArray

from flopy4.mf6.spec import field
from flopy4.mf6.utl.ncf_base import NcfBase


@attrs.define(kw_only=True, slots=False)
class Ncf(NcfBase):
    dfn_name: ClassVar[str] = "utl-ncf"

    deflate: Optional[int] = field(default=None, block="options", optional=True)
    shuffle: bool = field(default=False, block="options", optional=True)
    chunk_time: Optional[int] = field(default=None, block="options", optional=True)
    chunk_face: Optional[int] = field(default=None, block="options", optional=True)
    chunk_z: Optional[int] = field(default=None, block="options", optional=True)
    chunk_y: Optional[int] = field(default=None, block="options", optional=True)
    chunk_x: Optional[int] = field(default=None, block="options", optional=True)
    modflow6_attr_off: bool = field(default=False, block="options", optional=True)
    ncpl: Optional[int] = field(default=None, block="dimensions", optional=True)
    latitude: Optional[NDArray[np.float64]] = field(
        default=None, block="griddata", shape=("ncpl",), layered=False
    )
    longitude: Optional[NDArray[np.float64]] = field(
        default=None, block="griddata", shape=("ncpl",), layered=False
    )
