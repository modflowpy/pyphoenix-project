from abc import ABC
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import attrs

from flopy4.mf6.package import Package
from flopy4.spec import reference

if TYPE_CHECKING:
    from flopy4.mf6.model import Model


def _connects(side: int):
    """A check that a model on `side` (0 for a, 1 for b) is of the type the
    exchange connects there (see `Exchange.model_types`)."""

    def check(exg: "Exchange", model: "Model") -> "str | None":
        mtype = exg.model_types[side]
        if type(model).dfn_name.partition("-")[0] == mtype:  # type: ignore[attr-defined]
            return None
        return (
            f"({type(exg).__name__}) needs a {mtype.upper()} model {'ab'[side]}, "
            f"not {model.name!r} ({type(model).__name__})"  # type: ignore[attr-defined]
        )

    return check


@attrs.define(kw_only=True, slots=False)
class Exchange(Package, ABC):
    exgtype: Optional[type] = attrs.field(default=None)  # type: ignore
    exgfile: Optional[Path] = attrs.field(default=None)  # type: ignore
    exgmnamea: "Model | str | None" = reference(many=False, check=_connects(0), required=True)
    """The first model the exchange connects, as an object or a name. The
    simulation owns its models; an exchange only refers to them."""
    exgmnameb: "Model | str | None" = reference(many=False, check=_connects(1), required=True)
    """The second model the exchange connects, as an object or a name."""

    @property
    def model_types(self) -> tuple[str, str]:
        """The types of the models the exchange connects, in order:
        ``("gwf", "gwt")`` for GWF-GWT. (Every MF6 model type has three
        letters.)"""
        pair = type(self).dfn_name.partition("-")[2]  # type: ignore[attr-defined]
        return pair[:3], pair[3:]
