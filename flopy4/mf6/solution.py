from abc import ABC
from typing import TYPE_CHECKING

import attrs
from attrs import Attribute

from flopy4.mf6.package import Package
from flopy4.spec import reference_names

if TYPE_CHECKING:
    from flopy4.mf6.model import Model


@attrs.define(kw_only=True, slots=False)
class Solution(Package, ABC):
    """A solution. Its `slnmnames` (generated, from its row in the
    simulation's name file), also `models`, are the models it solves, as
    objects or names. The simulation owns its models; a solution only
    refers to them. If a simulation has one solution and it lists no
    models, it solves them all. A solution given no parent joins its
    models' simulation, if they have one."""

    if TYPE_CHECKING:
        slnmnames: "list[Model | str]"

    @property
    def models(self) -> "list[Model | str]":
        """The models the solution solves: `slnmnames`, which the
        constructor also takes as `models`."""
        return self.slnmnames

    @models.setter
    def models(self, value) -> None:
        self.slnmnames = value

    def solves(self, model: "Model") -> bool:
        """Whether this kind of solution can solve the model's type: EMS
        solves particle tracking (PRT) models, IMS all the others."""
        is_prt = type(model).dfn_name.startswith("prt")  # type: ignore[attr-defined]
        return is_prt == (self.ftype == "EMS6")

    def _reference_problem(self, field: Attribute, model) -> "str | None":
        return self._cant_solve(model)

    def _row_value(self, attr: str):
        # a lone solution listing none solves them all
        if attr == "slnmnames":
            return reference_names(self._solved_models())
        return super()._row_value(attr)

    def _cant_solve(self, model: "Model") -> "str | None":
        """Why this solution can't solve the model, or None if it can."""
        if self.solves(model):
            return None
        return (
            f"({self.ftype.removesuffix('6')}) can't solve model "
            f"{model.name!r} ({type(model).__name__})"  # type: ignore[attr-defined]
        )

    def _solved_models(self) -> list:
        """The models this solution solves, resolved against its
        simulation (see `Simulation._solution_models`). Without one, the
        models as listed."""
        sim = self._parent
        if sim is None or not hasattr(sim, "_solution_models"):
            return list(self.slnmnames)
        return next(models for sln, models in sim._solution_models() if sln is self)
