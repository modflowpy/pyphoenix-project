from os import PathLike
from pathlib import Path
from warnings import warn

from flopy.discretization.modeltime import ModelTime
from modflow_devtools.misc import cd, run_cmd
from xattree import xattree

from flopy4.mf6.component import Component
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.model import Model
from flopy4.mf6.solution import Solution
from flopy4.mf6.spec import field
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
    workspace: Path = field(default=None)
    filename: str = field(default="mfsim.nam")

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        if self.filename != "mfsim.nam":
            warn(
                "Simulation filename must be 'mfsim.nam'.",
                UserWarning,
            )
            self.filename = "mfsim.nam"

    @property
    def path(self) -> Path:
        """Return the path to the simulation namefile."""
        if self.workspace is None:
            raise ValueError("Simulation has no workspace path.")
        return Path(self.workspace).expanduser().resolve() / self.filename

    @property
    def time(self) -> ModelTime:
        """Return the simulation time discretization."""
        return self.tdis.to_time()

    def run(self, exe: str | PathLike = "mf6", verbose: bool = False) -> None:
        """Run the simulation using the given executable."""
        if self.workspace is None:
            raise ValueError(f"Simulation {self.name} has no workspace path.")
        with cd(self.workspace):
            stdout, stderr, retcode = run_cmd(exe, verbose=verbose)
            if retcode != 0:
                raise RuntimeError(
                    f"Simulation {self.name}: {exe} failed to run with returncode "  # type: ignore
                    f"{retcode}, and error message:\n\n{stdout + stderr} "
                )

    def load(self, format="ascii"):
        """Load the simulation in the specified format."""
        with cd(self.workspace):
            super().load(format)

    def write(self, format="ascii"):
        """Write the simulation in the specified format."""
        with cd(self.workspace):
            super().write(format)
