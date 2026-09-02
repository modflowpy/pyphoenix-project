from attrs import define

from flopy4.mf6.component import Component
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.model import Model
from flopy4.mf6.package import Package
from flopy4.mf6.solution import Solution


def component_ftype(cls: type) -> str:
    """E.g. ``"GWF6"``, ``"CHD6"``."""
    cls_name = cls.__name__
    if issubclass(cls, Exchange):
        return f"{cls_name[:3].upper()}6-{cls_name[3:].upper()}6"
    if issubclass(cls, Solution):
        return f"{cls.slntype.upper()}6"  # type: ignore[attr-defined]
    if len(cls_name) == 4 and cls_name[3] in ("g", "a"):
        return f"{cls_name[0:3].upper()}6"
    return f"{cls_name.upper()}6"


@define
class Binding:
    """A serializable representation of a component."""

    type: str
    fname: str
    terms: tuple[str, ...] | None = None

    def to_tuple(self) -> tuple[str, ...]:
        if self.terms and any(self.terms):
            return (self.type, self.fname, *self.terms)
        else:
            return (self.type, self.fname)

    @classmethod
    def from_component(cls, component: Component) -> "Binding":
        def _get_binding_terms(component: Component) -> tuple[str, ...] | None:
            if isinstance(component, Exchange):
                return (component.exgmnamea, component.exgmnameb)  # type: ignore
            elif isinstance(component, Solution):
                return tuple(component.models)
            elif isinstance(component, (Model, Package)):
                # pname (an xattree-unmanaged field, see Component.pname)
                # preserves an explicit/loaded name that xattree's own
                # .name reconciliation can't hold for "list"/"only"-kind
                # children; falls back to .name (the common case, and
                # what dict-kind children already reconcile correctly).
                return (component.pname or component.name,)  # type: ignore
            return None

        return cls(
            type=component_ftype(type(component)),
            fname=component.filename or component.default_filename(),
            terms=_get_binding_terms(component),
        )
