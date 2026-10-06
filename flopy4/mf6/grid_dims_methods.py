import attrs

from flopy4.dimensions import DerivedDim


class GridDimsMethods:
    """Dimension-provider methods for the generated grid packages (DIS, DISV,
    DISU, ...); fields and derived dimensions come from the DFN."""

    def get_dims(self) -> dict[str, int]:
        """Get all dimensions: the DIMENSIONS block's, then the derived ones."""
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
