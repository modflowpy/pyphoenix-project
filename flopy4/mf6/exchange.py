from abc import ABC
from pathlib import Path
from typing import Optional

import attrs

from flopy4.mf6.package import Package


@attrs.define(kw_only=True, slots=False)
class Exchange(Package, ABC):
    exgtype: Optional[type] = attrs.field(default=None)  # type: ignore
    exgfile: Optional[Path] = attrs.field(default=None)  # type: ignore
    exgmnamea: Optional[str] = attrs.field(default=None)
    exgmnameb: Optional[str] = attrs.field(default=None)
