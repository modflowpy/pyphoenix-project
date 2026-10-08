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

    def default_filename(self) -> str:
        return f"{self.name}.nam"  # type: ignore
