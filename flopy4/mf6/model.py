from abc import ABC
from pathlib import Path

import attrs

from flopy4.mf6.context import Context
from flopy4.utils import to_path


@attrs.define(kw_only=True, slots=False)
class Model(Context, ABC):
    @property  # type: ignore[override]
    def workspace(self) -> Path:
        """The simulation's workspace, or the model's own if it has no
        simulation. MF6 resolves every path in every input file against
        the simulation's directory, so a model's filenames are relative
        to it too (`gwf/m.dis` for a model in a subdirectory)."""
        parent = self.__dict__.get("_parent")
        if isinstance(parent, Context):
            return parent.workspace
        return self.__dict__.get("_workspace")  # type: ignore[return-value]

    @workspace.setter
    def workspace(self, value) -> None:
        """Set a model's own workspace. Under a simulation, the model's
        workspace is the simulation's: set that instead."""
        value = to_path(value)
        parent = self.__dict__.get("_parent")
        if isinstance(parent, Context) and value is not None and value != parent.workspace:
            raise ValueError(
                f"{self.name}: a model's workspace is its simulation's "  # type: ignore[attr-defined]
                f"({parent.workspace}); set the simulation's workspace instead"
            )
        self.__dict__["_workspace"] = value

    @property
    def solution(self):
        """The solution that solves this model, or `None` if it has no
        simulation or no solution does. Set it by listing the model in a
        solution's `models`."""
        sim = self.__dict__.get("_parent")
        if sim is None or not hasattr(sim, "_solution_models"):
            return None
        return next(
            (sln for sln, models in sim._solution_models() if any(m is self for m in models)),
            None,
        )

    @property
    def exchanges(self) -> list:
        """The exchanges that connect this model to others; empty if it
        has no simulation. Set them by naming the model in an exchange's
        `exgmnamea` or `exgmnameb`."""
        sim = self.__dict__.get("_parent")
        if sim is None or not hasattr(sim, "_exchange_models"):
            return []
        return [exg for exg, models in sim._exchange_models() if any(m is self for m in models)]

    def default_filename(self) -> str:
        return f"{self._name_or_class()}.nam"
