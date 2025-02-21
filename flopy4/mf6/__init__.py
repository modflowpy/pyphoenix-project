from abc import ABC
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from attr import field
from attrs import define
from numpy.typing import NDArray
from xattree import array, dim, xattree

__all__ = [
    "Component",
    "Package",
    "Model",
    "Simulation",
    "Solution",
    "Exchange",
    "COMPONENTS",
]

COMPONENTS = {}
"""MF6 component registry."""


class Component(ABC):
    @classmethod
    def __attrs_init_subclass__(cls):
        COMPONENTS[cls.__name__.lower()] = cls


@define
class Package(Component):
    pass


@define
class Model(Component):
    pass


@define
class Solution(Package):
    pass


@define
class Exchange(Package):
    exgtype: type = field()
    exgfile: Path = field()
    exgmnamea: Optional[str] = field(default=None)
    exgmnameb: Optional[str] = field(default=None)


@xattree
class Tdis(Package):
    @define
    class PeriodData:
        perlen: float = field(default=1.0)
        nstp: int = field(default=1)
        tsmult: float = field(default=1.0)

    nper: int = dim(
        coord="kper",
        scope="simulation",
        default=1,
        metadata={"block": "dimensions"},
    )
    perioddata: NDArray[np.object_] = array(
        PeriodData,
        dims=("nper",),
        metadata={"block": "perioddata"},
    )
    time_units: Optional[str] = field(
        default=None, metadata={"block": "options"}
    )
    start_date_time: Optional[datetime] = field(
        default=None, metadata={"block": "options"}
    )


@xattree
class Simulation(Component):
    models: dict[str, Model] = field()
    exchanges: dict[str, Exchange] = field()
    solutions: dict[str, Solution] = field()
    tdis: Tdis = field()
