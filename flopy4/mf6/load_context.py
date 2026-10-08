from collections.abc import Mapping
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any

import attrs

from flopy4.mf6.item import Item, infer_ncelldim

if TYPE_CHECKING:
    from flopy4.mf6.model import Model


@attrs.frozen
class LoadContext:
    """What a file's reader needs to know about where the file sits in
    the simulation. Passed down the tree as it loads, each level deriving
    its children's context from its own with `attrs.evolve`."""

    workspace: Path | None = attrs.field(default=None, converter=attrs.converters.optional(Path))
    """The simulation directory. Like MF6, every relative path in every
    input file resolves here, not against the file that names it."""

    dims: Mapping[str, int] = attrs.field(factory=dict, converter=lambda d: dict(d or {}))
    """Grid dims in scope: the model's discretization, or given."""

    parent: type | None = None
    """The class of the component whose file named this one, which tells
    how to read some of its values (see OBS's ids)."""

    exchange: "tuple[Model, Model] | None" = None
    """The models an exchange connects, whose grids give its cellids'
    widths. Inherited by the exchange's children (GNC, MVR, OBS)."""

    def resolve(self, path: str | PathLike) -> Path:
        """A path as written in an input file, resolved against the
        workspace. Absolute paths are returned as is."""
        path = Path(path)
        if path.is_absolute():
            return path
        if self.workspace is None:
            raise ValueError(f"{path}: no workspace to resolve against")
        return self.workspace / path

    def ncelldim(
        self,
        item_cls: type[Item],
        rows: list,
        sizes: Mapping[str, int] | None = None,
    ) -> int | Mapping[str, int]:
        """The width of `item_cls`'s cellids in `rows`. Under an exchange,
        each cellid column's, by name, from the grid of the model the
        column refers to (its ``cellid`` metadata: ``"1"`` for
        ``exgmnamea``, ``"2"`` for ``exgmnameb``, from the DFN). Otherwise
        from the dims if they say, else from the rows."""
        cellids = {
            f.name: f.metadata["cellid"] for f in item_cls.fields() if f.metadata.get("cellid")
        }
        widths = self._exchange_widths()
        if cellids and widths and all(model in widths for model in cellids.values()):
            return {name: widths[model] for name, model in cellids.items()}
        return infer_ncelldim(rows, item_cls, sizes=sizes, dims=dict(self.dims))

    def _exchange_widths(self) -> dict[str, int] | None:
        """The cellid width of each model the exchange connects, keyed
        as a cellid column names it (``"1"``, ``"2"``), or None if not
        under an exchange or either model has no discretization package."""
        if self.exchange is None:
            return None
        widths = {}
        for key, model in zip(("1", "2"), self.exchange):
            dis: Any = getattr(model, "dis", None)
            if dis is None or (width := dis.get_dims().get("ncelldim")) is None:
                return None
            widths[key] = width
        return widths
