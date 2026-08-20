from attrs import define

from flopy4.mf6.component import Component
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.model import Model
from flopy4.mf6.package import Package
from flopy4.mf6.solution import Solution


def component_ftype(cls: type) -> str:
    """The MF6 file-type token (e.g. ``"GWF6"``, ``"CHD6"``) for a
    concrete `Component` subclass.

    Pure function of the class, not an instance -- `Solution.slntype` is a
    `ClassVar`, so it's readable without constructing anything.

    G/A-variant package classes (``Chdg``, ``Drng``, ``Evta``, ``Ghbg``,
    ``Rcha``, ``Rivg``, ``Welg``) share their base's namefile ftype --
    confirmed against real MF6 source (`gwf.f90`'s package-type `select
    case`, e.g. `case ('CHD6')`, has no `'CHDG6'`/`'RCHA6'`/etc. arm at
    all; `chd_create` handles both variants once dispatched). A DFN-level
    `dfn_file_name`/legacy-flopy `_package_type` of `"gwf-chdg"` describes
    the DFN/class identity, not the namefile-level ftype token -- don't
    infer the latter from the former; a real MF6 run rejects the
    unabridged token with "Model package type not supported".
    """
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
        def _get_binding_terms(component: Component) -> tuple[str, ...] | None:
            if isinstance(component, Exchange):
                return (component.exgmnamea, component.exgmnameb)  # type: ignore
            elif isinstance(component, Solution):
                return tuple(component.models)
            elif isinstance(component, (Model, Package)):
                return (component.name,)  # type: ignore
            return None

        return cls(
            type=component_ftype(type(component)),
            fname=component.filename or component.default_filename(),
            terms=_get_binding_terms(component),
        )
