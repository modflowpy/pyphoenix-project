from abc import ABC

from pydantic.dataclasses import dataclass

from flopy4.mf6.context import CFG, Context


@dataclass(config=CFG, kw_only=True)
class Model(Context, ABC):
    def default_filename(self) -> str:
        return f"{self.name}.nam"  # type: ignore
