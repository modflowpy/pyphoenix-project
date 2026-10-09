from typing import ClassVar

import attrs

from flopy4.dimensions import DerivedDim


class DimsProviderMethods:
    """Dimension-provider methods for generated components whose DFN shares
    some of their dimensions beyond the component (the grid packages' model
    dimensions, TDIS's nper). Codegen names those in `shared_dims`, from the
    DFN's dimension scopes; fields and derived dimensions come from the DFN."""

    shared_dims: ClassVar[tuple[str, ...]] = ()

    def _own_dims(self) -> dict[str, int]:
        """All the component's own dimensions: the DIMENSIONS block's, then
        the derived ones, shared or not."""
        self._sync_dims()  # type: ignore[attr-defined]
        names = [
            f.name
            for f in attrs.fields(type(self))  # type: ignore[arg-type]
            if f.metadata.get("block") == "dimensions"
        ]
        names += [
            name
            for cls in reversed(type(self).__mro__)
            for name, attr in vars(cls).items()
            if isinstance(attr, DerivedDim)
        ]
        dims = {name: getattr(self, name) for name in names}
        return {name: value for name, value in dims.items() if value is not None}

    def get_dims(self) -> dict[str, int]:
        """Get the dimensions the component shares with others."""
        dims = self._own_dims()
        return {name: dims[name] for name in self.shared_dims if name in dims}
