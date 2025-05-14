from pathlib import Path

import attrs
from xattree import field, xattree

from flopy4.mf6.component import Component
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.model import Model
from flopy4.mf6.solution import Solution
from flopy4.mf6.tdis import Tdis

from flopy.discretization.modeltime import ModelTime


def convert_time(value):
    if isinstance(value, ModelTime):
        return Tdis.from_time(value)
    if isinstance(value, Tdis):
        return value
    raise TypeError(
        f"Expected ModelTime or Tdis, got {type(value)}"
    )

@xattree
class Simulation(Component):
    models: dict[str, Model] = field()
    exchanges: dict[str, Exchange] = field()
    solutions: dict[str, Solution] = field()
    sim_ws: Path = field(default=None)
    tdis: Tdis = field(converter=convert_time)
