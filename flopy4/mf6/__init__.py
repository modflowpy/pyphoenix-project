from abc import ABC
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import Optional

from attr import Factory, define, field

from flopy4 import component, init_tree, setattribute

__all__ = [
    "Component",
    "Package",
    "Model",
    "Simulation",
    "Sim",
    "COMPONENTS",
]

COMPONENTS = {}  # component registry


class Component(ABC):
    name: Optional[str] = None
    path: Optional[Path] = None

    def __init__(self, name=None, path=None):
        self.name = name
        self.path = path

    @classmethod
    def __attrs_init_subclass__(cls):
        COMPONENTS[cls.__name__.lower()] = cls


class Package(Component):
    def __init__(self, name=None, path=None):
        super().__init__(name, path)


class Model(Component):
    def __init__(self, name=None, path=None):
        super().__init__(name, path)


@component
@define(init=False, slots=False, on_setattr=setattribute)
class Tdis(Package):
    @define(slots=False)
    class PeriodData:
        perlen: float = field(default=1.0)
        nstp: int = field(default=1)
        tsmult: float = field(default=1.0)

    nper: int = field(default=1, metadata={"block": "dimensions"})
    perioddata: list[PeriodData] = field(
        default=Factory(list),
        metadata={"block": "perioddata", "shape": ("nper",)},
    )
    time_units: Optional[str] = field(
        default=None, metadata={"block": "options"}
    )
    start_date_time: Optional[datetime] = field(
        default=None, metadata={"block": "options"}
    )

    def __init__(
        self,
        sim=None,
        name=None,
        path=None,
        nper=1,
        perioddata=None,
        time_units=None,
        start_date_time=None,
    ):
        super().__init__(name, path)
        init_tree(
            self,
            parent=sim,
            nper=nper,
            perioddata=perioddata,
            time_units=time_units,
            start_date_time=start_date_time,
        )


class Solution(Package):
    def __init__(self, name=None, path=None):
        super().__init__(name, path)


@define(init=False, slots=False)
class Exchange(Package):
    exgtype: type = field()
    exgfile: Path = field()
    exgmnamea: Optional[str] = field(default=None)
    exgmnameb: Optional[str] = field(default=None)

    def __init__(
        self,
        name=None,
        path=None,
        mnamea=None,
        mnameb=None,
    ):
        super().__init__(name, path)
        self.exgtype = type(self)
        self.exgfile = path
        self.exgmnamea = mnamea
        self.exgmnameb = mnameb


class Simulation(Component):
    exe: Path

    def __init__(self, name=None, path=None, exe=None):
        super().__init__(name, path)
        self.exe = exe or which("mf6")


@component
@define(init=False, slots=False)
class Sim(Simulation):
    # tdis: Tdis = field(metadata={"block": "timing"})
    # models: dict[str, Model] = field(metadata={"block": "models"})
    # exchanges: dict[str, Exchange] = field(metadata={"block": "exchanges"})
    # solutions: dict[str, Solution] = field(metadata={"block": "solutions"})

    def __init__(
        self,
        name=None,
        path=None,
        exe=None,
        tdis=None,
        models=None,
        exchanges=None,
        solutions=None,
    ):
        super().__init__(name, path, exe)
        # TODO pull init_tree(self) call into @component definition
        init_tree(
            self,
            # children={
            #     "tdis": tdis,
            #     "models": models,
            #     "exchanges": exchanges,
            #     "solutions": solutions,
            # },
        )
