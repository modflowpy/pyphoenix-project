from pathlib import Path

from flopy4.mf6.codec import dump, load
from flopy4.mf6.component import Component
from flopy4.uio import DEFAULT_REGISTRY


def _default_filename(component: Component) -> str:
    """Default path for a component, based on its name."""
    if filename := component.filename:
        return filename
    name = component.name  # type: ignore
    cls_name = component.__class__.__name__.lower()
    return f"{name}.{cls_name}"


def _path(component: Component) -> str:
    """Default path for a component, based on its name."""
    if hasattr(component, "path") and component.path is not None:
        path = Path(component.path).expanduser().resolve()
        if path.is_dir():
            return str(path / _default_filename(component))
        return str(path)
    return _default_filename(component)


DEFAULT_REGISTRY.register_loader(Component, "ascii", lambda component: load(_path(component)))
DEFAULT_REGISTRY.register_writer(
    Component, "ascii", lambda component: dump(component, _path(component))
)
