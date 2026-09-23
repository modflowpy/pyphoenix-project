from os import PathLike
from typing import ClassVar
from warnings import warn

from modflow_devtools.misc import cd, run_cmd
from pydantic.dataclasses import dataclass

from flopy4.mf6.context import CFG, Context
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.model import Model
from flopy4.mf6.solution import Solution
from flopy4.mf6.spec import field
from flopy4.mf6.tdis import Tdis
from flopy4.mf6.utils.time import Time


def convert_time(value):
    if isinstance(value, Time):
        return Tdis.from_time(value)
    if isinstance(value, Tdis):
        return value
    raise TypeError(f"Expected Time or Tdis, got {type(value)}")


@dataclass(config=CFG, kw_only=True)
class Simulation(Context):
    dfn_name: ClassVar[str] = "sim-nam"

    tdis: Tdis = field(block="timing", converter=convert_time, default_factory=Tdis)
    models: dict[str, Model] = field(block="models", default_factory=dict)
    exchanges: dict[str, Exchange] = field(block="exchanges", default_factory=dict)
    solutions: dict[str, Solution] = field(block="solutiongroup", default_factory=dict)

    def default_filename(self) -> str:
        return "mfsim.nam"

    def __post_init__(self):
        super().__post_init__()
        if self.filename != "mfsim.nam":
            if self.filename is not None:
                warn(
                    "Simulation filename must be 'mfsim.nam'.",
                    UserWarning,
                )
            self.filename = "mfsim.nam"
        # Re-propagate workspace to Simulation's own children (models/
        # exchanges/solutions/tdis) -- Context.__post_init__ (already run,
        # via super() above) only saw whatever was attached at ITS point
        # in the post-init chain; re-assigning through the property setter
        # (attrs' on_setattr=update_child_attr, ported -- see Context.
        # workspace) re-runs the propagation now that every field on this
        # concrete Simulation instance is attached.
        self.workspace = self.workspace

    @property
    def time(self) -> Time:
        """Return a `Time` object describing the simulation's time discretization."""
        return self.tdis.to_time()

    def to_xarray(self):
        """DataTree with Tdis data merged into root dataset."""
        tree = super().to_xarray()
        try:
            tdis_ds = self.tdis.to_xarray()
            result = tree.copy(deep=True)
            result.update(tdis_ds)
            return result
        except Exception:
            return tree

    def run(self, exe: str | PathLike = "mf6", verbose: bool = False) -> None:
        """Run the simulation using the given executable."""
        with cd(self.workspace):
            out, err, ret = run_cmd(exe, verbose=verbose)
            if ret != 0:
                raise RuntimeError(
                    f"Simulation {self.name}: {exe} failed with "  # type: ignore
                    f"return code {ret}, output:\n\n{out + err} "
                )
