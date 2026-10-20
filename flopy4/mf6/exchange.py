from abc import ABC
from functools import cache
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import attrs

from flopy4.mf6.package import Package
from flopy4.spec import reference

if TYPE_CHECKING:
    from flopy4.mf6.model import Model


def _connects(side: int):
    """Whether an exchange accepts a model on `side` (0 for a, 1 for b):
    one of the type it connects there (see `Exchange.model_classes`)."""
    return lambda exg, model: isinstance(model, exg.model_classes()[side])


@attrs.define(kw_only=True, slots=False)
class Exchange(Package, ABC):
    exgtype: Optional[type] = attrs.field(default=None)  # type: ignore
    exgfile: Optional[Path] = attrs.field(default=None)  # type: ignore
    exgmnamea: "Model | str | None" = reference(many=False, accepts=_connects(0), required=True)
    """The first model the exchange connects, as an object or a name. The
    simulation owns its models; an exchange only refers to them."""
    exgmnameb: "Model | str | None" = reference(many=False, accepts=_connects(1), required=True)
    """The second model the exchange connects, as an object or a name."""

    @classmethod
    def model_classes(cls) -> tuple[type, type]:
        """The classes of the models the exchange connects, in order:
        ``(Gwf, Gwt)`` for GWF-GWT."""
        return _model_classes(cls.dfn_name)  # type: ignore[attr-defined]


@cache
def _model_classes(dfn_name: str) -> tuple[type, type]:
    """The model classes an exchange's DFN name pairs (``"exg-gwfgwt"``),
    found by splitting the pair where both halves are model types."""
    from flopy4.mf6.component import FNAMES

    def model(mtype: str) -> type:
        # generated packages load lazily: import the model's to register it
        import_module(f"{__package__}.{mtype}")
        return FNAMES[f"{mtype}-nam"]

    pair = dfn_name.partition("-")[2]
    for i in range(1, len(pair)):
        try:
            return model(pair[:i]), model(pair[i:])
        except (ImportError, KeyError):
            continue
    raise ValueError(f"{dfn_name}: no model types make up {pair!r}")
