from attrs import define

from flopy4.mf6.component import Component
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.model import Model
from flopy4.mf6.package import Package
from flopy4.mf6.solution import Solution


@define
class Binding:
    """
    An MF6 component binding: a record representation of the
    component for writing to a parent component's name file.
    """

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
        def _get_binding_type(component: Component) -> str:
            cls_name = component.__class__.__name__
            if isinstance(component, Exchange):
                return f"{'-'.join([cls_name[:2], cls_name[3:]]).upper()}6"
            elif isinstance(component, Solution):
                return f"{component.slntype}6"
            else:
                if len(cls_name) == 4 and (cls_name[3] == "g" or cls_name[3] == "a"):
                    return f"{cls_name[0:3]}6"
                return f"{cls_name.upper()}6"

        def _get_binding_terms(component: Component) -> tuple[str, ...] | None:
            if isinstance(component, Exchange):
                return (component.exgmnamea, component.exgmnameb)  # type: ignore
            elif isinstance(component, Solution):
                return tuple(component.models)
            elif isinstance(component, (Model, Package)):
                return (component.name,)  # type: ignore
            return None

        return cls(
            type=_get_binding_type(component),
            fname=component.filename or component.default_filename(),
            terms=_get_binding_terms(component),
        )
