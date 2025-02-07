from abc import ABC
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import Optional

from attr import Factory, define, field

from flopy4 import component, init_tree, setattribute

__all__ = ["Component", "Package", "Model", "Sim", "Simulation"]


class Component(ABC):
    name: Optional[str] = None
    path: Optional[Path] = None

    def __init__(self, name=None, path=None):
        self.name = name
        self.path = path


class Package(Component):
    def __init__(self, name=None, path=None):
        super().__init__(name, path)


class Model(Component):
    def __init__(self, name=None, path=None):
        super().__init__(name, path)


class Sim(Component):
    exe: Path

    def __init__(self, name=None, path=None, exe=None):
        super().__init__(name, path)
        self.exe = exe or which("mf6")


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
        metadata={"block": "perioddata", "shape": "(nper)"},
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


@component
@define(init=False, slots=False, on_setattr=setattribute)
class Simulation(Sim):
    def __init__(self, name=None, path=None, exe=None):
        super().__init__(name, path, exe)
        init_tree(self)
