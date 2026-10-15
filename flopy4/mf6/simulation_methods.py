from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING
from warnings import warn

from modflow_devtools.misc import cd, get_ostag, is_in_ci, run_cmd

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

    def run(  # type: ignore[misc]
        self: "Simulation",
        exe: str | PathLike = "mf6",
        verbose: bool = False,
        ncpus: int = 1,
    ) -> None:
        """Run the simulation using the given executable.

        Warns first if the executable's version doesn't match the MF6
        version flopy4.mf6 is synced to. With `ncpus` > 1, runs under MPI
        (`mpiexec -np <ncpus> <exe> -p`) for a partitioned simulation; success
        requires every rank to report normal termination, since mpiexec's own
        return code doesn't reliably reflect a single rank's failure.
        """
        from flopy4.mf6._compat import check_mf6_compatibility

        with cd(self.workspace):
            check_mf6_compatibility(exe)
            if ncpus > 1:
                if not is_in_ci() and get_ostag() == "mac":
                    # mac's OpenMPI needs a hostfile to run more ranks than cores
                    Path("localhost").write_text(f"localhost slots={ncpus}\n")
                    launch_opts = ["--hostfile", "localhost"]
                elif get_ostag() == "win64":
                    launch_opts = []
                else:
                    launch_opts = ["--oversubscribe"]
                args = ["mpiexec", *launch_opts, "-np", str(ncpus), str(exe), "-p"]
            else:
                args = [str(exe)]
            out, err, ret = run_cmd(*args, verbose=verbose)
            if ncpus > 1:
                success = (out + err).lower().count("normal termination") == ncpus
            else:
                success = ret == 0
            if not success:
                raise RuntimeError(
                    f"Simulation {self.name}: {exe} failed with "
                    f"return code {ret}, output:\n\n{out + err} "
                )
