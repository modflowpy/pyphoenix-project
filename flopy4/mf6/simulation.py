from os import PathLike
from pathlib import Path
from typing import ClassVar

from flopy.discretization.modeltime import ModelTime
from modflow_devtools.misc import cd, run_cmd
from xattree import field, xattree

from flopy4.mf6.component import Component
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.model import Model
from flopy4.mf6.solution import Solution
from flopy4.mf6.tdis import Tdis


def convert_time(value):
    if isinstance(value, ModelTime):
        return Tdis.from_time(value)
    if isinstance(value, Tdis):
        return value
    raise TypeError(f"Expected ModelTime or Tdis, got {type(value)}")


@xattree
class Simulation(Component):
    models: dict[str, Model] = field()
    exchanges: dict[str, Exchange] = field()
    solutions: dict[str, Solution] = field()
    tdis: Tdis = field(converter=convert_time)
    # TODO: decorator for components bound
    # to some directory or file path?
    path: Path = field(default=None)
    filename: ClassVar[str] = "mfsim.nam"

    @property
    def time(self) -> ModelTime:
        return self.tdis.to_time()

    def run(self, exe: str | PathLike = "mf6", verbose: bool = False) -> None:
        """Run the simulation using the given executable."""
        if self.path is None:
            raise ValueError(f"Simulation {self.name} has no workspace path.")
        with cd(self.path):
            stdout, stderr, retcode = run_cmd(exe, verbose=verbose)
            if retcode != 0:
                raise RuntimeError(
                    f"Simulation {self.name}: {exe} failed to run with returncode "  # type: ignore
                    f"{retcode}, and error message:\n\n{stdout + stderr} "
                )

    def load(self, format):
        with cd(self.path):
            super().load(format)

    def write(self, format):
        with cd(self.path):
            super().write(format)
