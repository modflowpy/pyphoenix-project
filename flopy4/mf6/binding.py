from pathlib import Path

from attrs import define

from flopy4.mf6.component import FTYPES, Component
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.model import Model
from flopy4.mf6.package import Package
from flopy4.mf6.solution import Solution


def _resolve_component_class(binding_type: str) -> type[Component]:
    """
    Map binding type string to component class using the FTYPES registry.

    The binding type is parsed to extract the ftype (e.g., 'gwf6' -> 'gwf',
    'gwf-gwf6' -> 'gwf-gwf') and looked up in the FTYPES registry, which
    is populated automatically when Component subclasses are defined.

    Parameters
    ----------
    binding_type : str
        Binding type string (e.g., 'gwf6', 'ims6', 'gwf-gwf6')

    Returns
    -------
    type[Component]
        Component class

    Raises
    ------
    ValueError
        If the binding type is not found in the FTYPES registry
    """
    # Normalize to lowercase
    binding_type = binding_type.lower()

    # Strip the '6' suffix to get the ftype
    if binding_type.endswith("6"):
        ftype = binding_type[:-1]
    else:
        ftype = binding_type

    # Look up in the FTYPES registry
    if ftype in FTYPES:
        return FTYPES[ftype]

    raise ValueError(
        f"Unknown binding type: {binding_type}. "
        f"No component with ftype='{ftype}' is registered. "
        f"Available ftypes: {sorted(FTYPES.keys())}"
    )


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
                    return f"{cls_name[0:3].upper()}6"
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

    @classmethod
    def to_component(cls, binding_tuple: tuple | list, workspace: Path) -> Component:
        """
        Resolve binding tuple to component instance (inverse of from_component).

        Parameters
        ----------
        binding_tuple : tuple | list
            Binding in form (type, fname) or (type, fname, *terms)
        workspace : Path
            Workspace directory for resolving file paths

        Returns
        -------
        Component
            Loaded component instance
        """
        # Extract binding parts
        binding_type = binding_tuple[0]
        fname = binding_tuple[1]
        terms = binding_tuple[2:] if len(binding_tuple) > 2 else ()

        # Resolve component class from type string
        component_cls = _resolve_component_class(binding_type)

        # Recursively load the component
        component_path = workspace / fname
        component = component_cls.load(component_path)

        # Apply terms (e.g., set name from binding if provided)
        # For models/packages, first term is the name
        if terms and hasattr(component, "name"):
            component.name = terms[0]  # type: ignore[attr-defined]

        return component  # type: ignore[return-value]
