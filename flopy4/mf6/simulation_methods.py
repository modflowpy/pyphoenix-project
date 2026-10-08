from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING
from warnings import warn

from modflow_devtools.misc import cd, run_cmd

from flopy4.mf6.utils.time import Time

if TYPE_CHECKING:
    from flopy4.mf6.context import Context
    from flopy4.mf6.simulation import Simulation


class SimulationMethods:
    """Methods for the generated `Simulation`; fields come from the DFN."""

    def default_filename(self) -> str:
        return "mfsim.nam"

    def __attrs_post_init__(self) -> None:
        super().__attrs_post_init__()  # type: ignore[misc]
        sim: "Context" = self  # type: ignore[assignment]
        if sim.filename != Path("mfsim.nam"):
            if sim.filename is not None:
                warn(
                    "Simulation filename must be 'mfsim.nam'.",
                    UserWarning,
                )
            sim.filename = Path("mfsim.nam")

    @property
    def time(self: "Simulation") -> Time:  # type: ignore[misc]
        """Return a `Time` object describing the simulation's time discretization."""
        return self.tdis.to_time()

    def to_xarray(self: "Simulation"):  # type: ignore[misc]
        """DataTree with Tdis data merged into root dataset."""
        tree = super().to_xarray()  # type: ignore[misc]
        try:
            tdis_ds = self.tdis.to_xarray()
            result = tree.copy(deep=True)
            result.update(tdis_ds)
            return result
        except Exception:
            return tree

    def run(self: "Simulation", exe: str | PathLike = "mf6", verbose: bool = False) -> None:  # type: ignore[misc]
        """Run the simulation using the given executable.

        Warns first if the executable's version doesn't match the MF6
        version flopy4.mf6 is synced to.
        """
        from flopy4.mf6._compat import check_mf6_compatibility

        with cd(self.workspace):
            check_mf6_compatibility(exe)
            out, err, ret = run_cmd(exe, verbose=verbose)
            if ret != 0:
                raise RuntimeError(
                    f"Simulation {self.name}: {exe} failed with "
                    f"return code {ret}, output:\n\n{out + err} "
                )
