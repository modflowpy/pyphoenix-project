from abc import ABC

import attrs

from flopy4.mf6.context import Context


@attrs.define(kw_only=True, slots=False)
class Model(Context, ABC):
    def default_filename(self) -> str:
        return f"{self.name}.nam"  # type: ignore
