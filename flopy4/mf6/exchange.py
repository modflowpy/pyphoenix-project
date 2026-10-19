from abc import ABC
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import attrs

from flopy4.mf6.package import Package
from flopy4.mf6.spec import reference

if TYPE_CHECKING:
    from flopy4.mf6.model import Model


@attrs.define(kw_only=True, slots=False)
class Exchange(Package, ABC):
    exgtype: Optional[type] = attrs.field(default=None)  # type: ignore
    exgfile: Optional[Path] = attrs.field(default=None)  # type: ignore
    exgmnamea: "Model | str | None" = reference(many=False)
    """The first model the exchange connects, as an object or a name. The
    simulation owns its models; an exchange only refers to them."""
    exgmnameb: "Model | str | None" = reference(many=False)
    """The second model the exchange connects, as an object or a name."""

    @property
    def model_types(self) -> tuple[str, str]:
        """The types of the models the exchange connects, in order:
        ``("gwf", "gwt")`` for GWF-GWT."""
        pair = type(self).dfn_name.partition("-")[2]  # type: ignore[attr-defined]
        return pair[:3], pair[3:]
