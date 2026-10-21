from abc import ABC
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import attrs
from attrs import Attribute

from flopy4.mf6.package import Package

if TYPE_CHECKING:
    from flopy4.mf6.model import Model


@attrs.define(kw_only=True, slots=False)
class Exchange(Package, ABC):
    """An exchange. Its `exgmnamea` and `exgmnameb` (generated, from its
    row in the simulation's name file) are the models it connects, as
    objects or names, of the types in `model_types`. The simulation owns
    its models; an exchange only refers to them."""

    exgtype: Optional[type] = attrs.field(default=None)  # type: ignore
    exgfile: Optional[Path] = attrs.field(default=None)  # type: ignore
    if TYPE_CHECKING:
        exgmnamea: "Model | str | None"
        exgmnameb: "Model | str | None"

    @property
    def model_types(self) -> tuple[str, str]:
        """The types of the models the exchange connects, in order:
        ``("gwf", "gwt")`` for GWF-GWT. (Every MF6 model type has three
        letters.)"""
        pair = type(self).dfn_name.partition("-")[2]  # type: ignore[attr-defined]
        return pair[:3], pair[3:]

    def _reference_problem(self, field: Attribute, model) -> "str | None":
        """A problem if the model isn't of the type the exchange connects on
        the field's side (its references are a's, then b's, in row order)."""
        side = [f.name for f in self._reference_fields()].index(field.name)
        mtype = self.model_types[side]
        if type(model).dfn_name.partition("-")[0] == mtype:
            return None
        return (
            f"({type(self).__name__}) needs a {mtype.upper()} model {'ab'[side]}, "
            f"not {model.name!r} ({type(model).__name__})"
        )
