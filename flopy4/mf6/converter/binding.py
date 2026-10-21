from attrs import define

from flopy4.mf6.component import Component
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.model import Model
from flopy4.mf6.package import Package
from flopy4.mf6.solution import Solution
from flopy4.spec import reference_names


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


def _flat(values) -> list:
    """Reference fields' values as a row's terms, lists spread out."""
    return [v for value in values for v in (value if isinstance(value, list) else [value])]


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
            if isinstance(component, Solution):
                # a lone solution listing none solves them all
                return tuple(reference_names(component._solved_models()))
            if refs := component._reference_fields():
                # the reference fields are the row's terms, in order
                return tuple(_flat(reference_names(getattr(component, f.name)) for f in refs))
            if isinstance(component, (Model, Package)):
                return (component.name,)  # type: ignore
            return None

        return cls(
            type=component_ftype(type(component)),
            fname=component.filename.as_posix(),
            terms=_get_binding_terms(component),
        )
