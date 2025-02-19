from abc import ABC
from datetime import datetime
from pathlib import Path
from typing import Optional

from attr import Factory, field
from attrs import define
from xattree import array, child, xattree

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


class Package(Component):
    pass


class Model(Component):
    pass


class Solution(Package):
    pass


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

    nper: int = field(
        default=1,
        metadata={
            "block": "dimensions",
            "dim": {"coord": "kper", "scope": "simulation"},
        },
    )
    perioddata: list[PeriodData] = array(
        dims=("nper",),
        default=Factory(list),
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
    models: dict[str, Model] = child(dict[str, Model])
    exchanges: dict[str, Exchange] = child(dict[str, Exchange])
    solutions: dict[str, Solution] = child(dict[str, Solution])
    tdis: Tdis = child(Tdis)
