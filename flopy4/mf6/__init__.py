from abc import ABC
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from attrs import define
from numpy.typing import NDArray
from xattree import ROOT, array, dim, field, xattree

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
        perlen: float
        nstp: int
        tsmult: float

    nper: int = dim(
        name="per",
        default=1,
        scope=ROOT,
        metadata={"block": "dimensions"},
    )
    time_units: Optional[str] = field(
        default=None, metadata={"block": "options"}
    )
    start_date_time: Optional[datetime] = field(
        default=None, metadata={"block": "options"}
    )
    # perioddata: NDArray[np.object_] = array(
    #     PeriodData,
    #     dims=("per",),
    #     metadata={"block": "perioddata"},
    # )
    perlen: NDArray[np.floating] = array(
        default=1.0,
        dims=("per",),
        metadata={"block": "perioddata"},
    )
    nstp: NDArray[np.integer] = array(
        default=1,
        dims=("per",),
        metadata={"block": "perioddata"},
    )
    tsmult: NDArray[np.floating] = array(
        default=1.0,
        dims=("per",),
        metadata={"block": "perioddata"},
    )


@xattree
class Simulation(Component):
    models: dict[str, Model] = field()
    exchanges: dict[str, Exchange] = field()
    solutions: dict[str, Solution] = field()
    tdis: Tdis = field()
