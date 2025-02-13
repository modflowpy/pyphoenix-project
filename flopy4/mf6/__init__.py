from abc import ABC
from datetime import datetime
from pathlib import Path
from typing import Optional

from attr import Factory, define, field

from flopy4 import component, setattribute

__all__ = [
    "Component",
    "Package",
    "Model",
    "Simulation",
    "Sim",
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


@component
@define(slots=False, on_setattr=setattribute)
class Tdis(Package):
    @define(slots=False)
    class PeriodData:
        perlen: float = field(default=1.0)
        nstp: int = field(default=1)
        tsmult: float = field(default=1.0)

    nper: int = field(default=1, metadata={"block": "dimensions"})
    perioddata: list[PeriodData] = field(
        default=Factory(list),
        metadata={"block": "perioddata", "dims": ("nper",)},
    )
    time_units: Optional[str] = field(
        default=None, metadata={"block": "options"}
    )
    start_date_time: Optional[datetime] = field(
        default=None, metadata={"block": "options"}
    )


class Solution(Package):
    pass


class Exchange(Package):
    exgtype: type = field()
    exgfile: Path = field()
    exgmnamea: Optional[str] = field(default=None)
    exgmnameb: Optional[str] = field(default=None)


class Simulation(Component):
    pass


@component
@define(init=False, slots=False)
class Sim(Simulation):
    # "bind" indicates this is a subcomponent, not a variable.
    # TODO: add separate `component()` decorator like `field`?
    models: dict[str, Model] = field(metadata={"bind": True})
    exchanges: dict[str, Exchange] = field(metadata={"bind": True})
    solutions: dict[str, Solution] = field(metadata={"bind": True})
    tdis: Tdis = field(metadata={"bind": True}, default=Factory(Tdis))
