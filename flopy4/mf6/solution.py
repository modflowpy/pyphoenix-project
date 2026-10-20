from abc import ABC
from typing import TYPE_CHECKING, ClassVar

import attrs

from flopy4.mf6.package import Package
from flopy4.mf6.spec import reference, reference_names

if TYPE_CHECKING:
    from flopy4.mf6.model import Model


@attrs.define(kw_only=True, slots=False)
class Solution(Package, ABC):
    slntype: ClassVar[str] = "sln"
    models: "list[Model | str]" = reference()
    """The models this solution solves, as objects or names. The simulation
    owns its models; a solution only refers to them. If a simulation has
    one solution and it lists no models, it solves them all. A solution
    given no parent joins its models' simulation, if they have one."""

    def __attrs_post_init__(self) -> None:
        # no parent given: join the simulation the listed models belong to
        if self._parent is None:
            sims = {
                id(sim): sim
                for m in self.models
                if not isinstance(m, str)
                and hasattr(sim := m.__dict__.get("_parent"), "_solution_models")
            }
            if len(sims) > 1:
                names = reference_names(self.models)
                raise ValueError(f"{self.name}: models {names} belong to different simulations")
            if sims:
                self._parent = next(iter(sims.values()))
        super().__attrs_post_init__()

    def solves(self, model: "Model") -> bool:
        """Whether this kind of solution can solve the model's type: EMS
        solves particle tracking (PRT) models, IMS all the others."""
        is_prt = type(model).dfn_name.startswith("prt")  # type: ignore[attr-defined]
        return is_prt == (self.slntype == "ems")

    def _solved_models(self) -> list:
        """The models this solution solves, resolved against its
        simulation (see `Simulation._solution_models`). Without one, the
        models as listed."""
        sim = self._parent
        if sim is None or not hasattr(sim, "_solution_models"):
            return list(self.models)
        return next(models for sln, models in sim._solution_models() if sln is self)
