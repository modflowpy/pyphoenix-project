from abc import ABC
from pathlib import Path
from typing import ClassVar, Optional

import attrs

from flopy4.mf6.package import Package
from flopy4.mf6.spec import field


@attrs.define(kw_only=True, slots=False)
class Exchange(Package, ABC):
    cellid_models: ClassVar[dict[str, int]] = {
        "cellidm1": 0,
        "cellidm2": 1,
        "cellidn": 0,
        "cellidsj": 0,
        "cellidm": 1,
    }
    """Which model each cellid column of the exchange and its GNC refers
    to: 0 for ``exgmnamea``, 1 for ``exgmnameb``. The DFNs don't say."""

    exgtype: Optional[type] = field(default=None)  # type: ignore
    exgfile: Optional[Path] = field(default=None)  # type: ignore
    exgmnamea: Optional[str] = field(default=None)
    exgmnameb: Optional[str] = field(default=None)

    def default_filename(self) -> str:
        return f"{self.name}.exg"  # type: ignore
