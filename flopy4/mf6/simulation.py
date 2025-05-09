from pathlib import Path

from xattree import field, xattree

from flopy4.mf6.component import Component
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.model import Model
from flopy4.mf6.solution import Solution
from flopy4.mf6.tdis import Tdis


@xattree
class Simulation(Component):
    sim_ws: Path = field()
    models: dict[str, Model] = field()
    exchanges: dict[str, Exchange] = field()
    solutions: dict[str, Solution] = field()
    tdis: Tdis = field()
