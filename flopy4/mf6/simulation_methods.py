from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING
from warnings import warn

from modflow_devtools.misc import cd, get_ostag, is_in_ci, run_cmd

if TYPE_CHECKING:
    from flopy4.mf6.context import Context
    from flopy4.mf6.simulation import Simulation
    from flopy4.mf6.solution import Solution
    from flopy4.mf6.utils.time import Time


class SimulationMethods:
    """Methods for the generated `Simulation`; fields come from the DFN."""

    def default_filename(self) -> str:
        return "mfsim.nam"

    def __attrs_post_init__(self) -> None:
        super().__attrs_post_init__()  # type: ignore[misc]
        sim: "Context" = self  # type: ignore[assignment]
        if sim._filename != Path("mfsim.nam"):
            if sim._filename is not None:
                warn(
                    "Simulation filename must be 'mfsim.nam'.",
                    UserWarning,
                )
            sim.filename = Path("mfsim.nam")

    def __setstate__(self, state) -> None:
        super().__setstate__(state)  # type: ignore[misc]
        # solutions and exchanges are pickled with their models' names
        # (see Component.__getstate__): resolve them, as loading does
        self._resolve_references()  # type: ignore[attr-defined]

    def write(self, *args, **kwargs) -> None:
        """Check the children's references (see `Component._reference_errors`)
        and the solution group (see `_solution_models`), then write."""
        sim: "Simulation" = self  # type: ignore[assignment]
        errors = [e for child in sim._children.values() for e in child._reference_errors()]
        if errors:
            raise ValueError("Invalid references: " + "; ".join(errors))
        self._solution_models(check=True)  # type: ignore[misc]
        super().write(*args, **kwargs)  # type: ignore[misc]

    def _solution_models(self: "Simulation", check: bool = False) -> list:  # type: ignore[misc]
        """Each solution with the models it solves, as pairs, models given
        by name resolved (see `Component._resolved`). The only solution,
        listing no models, solves them all. With `check`, raise if a model
        is solved by no solution or more than one, or the only solution
        can't solve one it solves by listing none. (`write` checks that the
        models listed are the simulation's, and of types the solutions
        solve, as it does any reference.)"""
        self._children  # names any unnamed models
        pairs: list[tuple[Solution, list]] = []
        for sln in self.solutiongroup:
            if not sln.models and len(self.solutiongroup) == 1:
                pairs.append((sln, list(self.models)))
            else:
                pairs.append((sln, sln._resolved("models")))
        if not check:
            return pairs
        errors = []
        for model in self.models:
            claims = [sln.name for sln, models in pairs if any(m is model for m in models)]
            if not claims:
                errors.append(f"model {model.name!r} isn't solved by any solution")
            elif len(claims) > 1:
                errors.append(f"model {model.name!r} is solved by more than one solution: {claims}")
        for sln, models in pairs:
            # listed models are checked as references; these are implied
            if not sln.models:
                errors.extend(
                    f"{sln.name} {problem}" for m in models if (problem := sln._cant_solve(m))
                )
        if errors:
            raise ValueError("Invalid solution group: " + "; ".join(errors))
        return pairs

    @property
    def time(self: "Simulation") -> "Time":  # type: ignore[misc]
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

        if ncpus < 1:
            raise ValueError(f"ncpus must be >= 1, got {ncpus}")

        with cd(self.workspace):
            check_mf6_compatibility(exe)
            hostfile = None
            if ncpus > 1:
                ostag = get_ostag()
                if not is_in_ci() and ostag == "mac":
                    # mac's OpenMPI needs a hostfile to run more ranks than cores
                    hostfile = Path("localhost")
                    hostfile.write_text(f"localhost slots={ncpus}\n")
                    launch_opts = ["--hostfile", "localhost"]
                elif ostag in ("win64", "win32"):
                    launch_opts = []
                else:
                    launch_opts = ["--oversubscribe"]
                args = ["mpiexec", *launch_opts, "-np", str(ncpus), str(exe), "-p"]
            else:
                args = [str(exe)]
            try:
                out, err, ret = run_cmd(*args, verbose=verbose)
            finally:
                if hostfile is not None:
                    hostfile.unlink(missing_ok=True)
            if ncpus > 1:
                normal = (out + err).lower().count("normal termination")
                success = normal == ncpus
                detail = f"{normal}/{ncpus} ranks reported normal termination"
            else:
                success = ret == 0
                detail = f"return code {ret}"
            if not success:
                raise RuntimeError(
                    f"Simulation {self.name}: {exe} failed with {detail}, output:\n\n{out + err} "
                )
