from os import PathLike
from warnings import warn

from modflow_devtools.misc import cd, run_cmd
from xattree import xattree

from flopy4.mf6.context import Context, update_child_attr
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.model import Model
from flopy4.mf6.solution import Solution
from flopy4.mf6.spec import xattree_field as field
from flopy4.mf6.tdis import Tdis
from flopy4.mf6.utils.time import Time


def convert_time(value):
    if isinstance(value, Time):
        return Tdis.from_time(value)
    if isinstance(value, Tdis):
        return value
    raise TypeError(f"Expected Time or Tdis, got {type(value)}")


@xattree
class Simulation(Context):
    tdis: Tdis = field(block="timing", converter=convert_time)
    models: dict[str, Model] = field(block="models")
    exchanges: dict[str, Exchange] = field(block="exchanges")
    solutions: dict[str, Solution] = field(block="solutiongroup")

    def default_filename(self) -> str:
        return "mfsim.nam"

    def __attrs_post_init__(self):
        from attrs import fields_dict

        super().__attrs_post_init__()
        if self.filename != "mfsim.nam":
            if self.filename is not None:
                warn(
                    "Simulation filename must be 'mfsim.nam'.",
                    UserWarning,
                )
            self.filename = "mfsim.nam"
        fields = fields_dict(type(self))
        field = fields["workspace"]
        update_child_attr(self, field, self.workspace)

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
