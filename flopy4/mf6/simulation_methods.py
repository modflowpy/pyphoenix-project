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
        sim: "Simulation" = self  # type: ignore[assignment]

        def find(m):
            # not `or`: an empty model is falsy
            return m if (found := sim._find_model(m)) is None else found

        for sln in sim.solutiongroup:
            sln.models = [find(m) for m in sln.models]
        for exg in sim.exchanges:
            exg.exgmnamea = find(exg.exgmnamea)
            exg.exgmnameb = find(exg.exgmnameb)

    def write(self, *args, **kwargs) -> None:
        """Check the solution group and exchanges (see `_solution_models`
        and `_exchange_models`), then write."""
        self._solution_models(check=True)  # type: ignore[misc]
        self._exchange_models(check=True)  # type: ignore[misc]
        super().write(*args, **kwargs)  # type: ignore[misc]

    def _find_model(self: "Simulation", model):  # type: ignore[misc]
        """The simulation's model given as a model or a name (looked up
        case-insensitively, as MF6 does), or None if it has no such model."""
        if model is None:
            return None
        if isinstance(model, str):
            return next((m for m in self.models if str(m.name).lower() == model.lower()), None)
        return next((m for m in self.models if m is model), None)

    def _exchange_models(self: "Simulation", check: bool = False) -> list:  # type: ignore[misc]
        """Each exchange with the two models it connects, as pairs. Models
        given by name are looked up as `_find_model` does; unresolved
        names stay as given. With `check`, raise if an exchange is missing
        a model, names one the simulation doesn't have, or connects models
        of types it doesn't (a GWF-GWT exchange connects a GWF model to a
        GWT model)."""
        self._children  # names any unnamed models
        errors = []
        pairs = []
        for exg in self.exchanges:
            models = []
            for side, m, mtype in zip("ab", (exg.exgmnamea, exg.exgmnameb), exg.model_types):
                found = self._find_model(m)
                if m is None:
                    errors.append(f"{exg.name} has no model {side} (exgmname{side})")
                elif found is None:
                    name = m if isinstance(m, str) else m.name
                    errors.append(f"{exg.name} names model {name!r}, which isn't in the simulation")
                elif _model_type(found) != mtype:
                    errors.append(
                        f"{exg.name} ({type(exg).__name__}) needs a {mtype.upper()} model "
                        f"{side}, not {found.name!r} ({type(found).__name__})"
                    )
                models.append(m if found is None else found)
            pairs.append((exg, tuple(models)))
        if check and errors:
            raise ValueError("Invalid exchanges: " + "; ".join(errors))
        return pairs

    def _solution_models(self: "Simulation", check: bool = False) -> list:  # type: ignore[misc]
        """Each solution with the models it solves, as pairs. A model given
        by name is looked up among the simulation's models, case-insensitively
        as MF6 does. The only solution, listing no models, solves them all.
        With `check`, raise if a solution lists a model the simulation
        doesn't have or can't solve its type, or if a model is solved by no
        solution or more than one. Unresolved names stay as given."""
        self._children  # names any unnamed models
        errors = []
        pairs: list[tuple[Solution, list]] = []
        for sln in self.solutiongroup:
            if not sln.models and len(self.solutiongroup) == 1:
                pairs.append((sln, list(self.models)))
                continue
            models = []
            for m in sln.models:
                found = self._find_model(m)
                if found is None:
                    name = m if isinstance(m, str) else m.name
                    errors.append(f"{sln.name} lists model {name!r}, which isn't in the simulation")
                models.append(m if found is None else found)
            pairs.append((sln, models))
        if not check:
            return pairs
        for model in self.models:
            claims = [sln.name for sln, models in pairs if any(m is model for m in models)]
            if not claims:
                errors.append(f"model {model.name!r} isn't solved by any solution")
            elif len(claims) > 1:
                errors.append(f"model {model.name!r} is solved by more than one solution: {claims}")
        for sln, models in pairs:
            for m in models:
                if not isinstance(m, str) and not sln.solves(m):
                    errors.append(
                        f"{sln.name} ({sln.slntype.upper()}) can't solve model "
                        f"{m.name!r} ({type(m).__name__})"
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


def _model_type(model) -> str:
    """A model's type, e.g. ``"gwf"``."""
    return type(model).dfn_name.partition("-")[0]
