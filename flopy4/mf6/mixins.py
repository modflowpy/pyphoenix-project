"""Mixins for dimension resolution in MF6 components.

This module provides reusable mixins that implement dimension resolution
infrastructure for MF6 components.
"""

import attrs
from attrs import define, field

from flopy4.mf6.protocols import DimensionProvider


@define
class DimensionRegistryMixin:
    """Mixin for containers that resolve dimensions from children via lazy tree walking.

    This mixin adds dimension resolution capabilities to any attrs class. It provides
    lazy, cached dimension resolution by walking the object graph to find dimension
    providers.

    The mixin must be an attrs class (@define) so it can define its own fields (_dimension_cache).
    Attrs properly handles multiple @define classes in inheritance chains.

    Attributes
    ----------
    _dimension_cache : dict[str, int]
        Cache of resolved dimensions for performance.

    Notes
    -----
    During Phases 1-2 (xattree coexistence), the _set_child_parents() method is a no-op
    since xattree already manages parent references. This will be enabled in Phase 3
    when parent management is migrated.
    """

    _dimension_cache: dict[str, int] = field(init=False, factory=dict, repr=False)

    def __attrs_post_init__(self) -> None:
        """Set parent references on all children after construction.

        This hook is called by attrs after __init__ completes. It chains to any
        parent class __attrs_post_init__ and then sets parent references on children.
        """
        if hasattr(super(), "__attrs_post_init__"):
            super().__attrs_post_init__()  # type: ignore[misc]
        self._set_child_parents()

    def _set_child_parents(self) -> None:
        """Walk all fields and set parent references on children.

        NOTE: During Phases 1-2 (xattree coexistence), this is a no-op since
        xattree already sets parent references. This method will be enabled
        in Phase 3 when we migrate parent management.

        When enabled, this will handle:
        - Direct children (single component fields)
        - Collections (dict/list of components)
        """
        # TODO Phase 3: Enable this when we remove @xattree
        # For now, xattree handles parent setting
        pass

        # Implementation to enable in Phase 3:
        # for field_obj in attrs.fields(type(self)):
        #     value = getattr(self, field_obj.name, None)
        #     if value is None:
        #         continue
        #     if hasattr(value, 'parent'):
        #         value.parent = self
        #     elif isinstance(value, dict):
        #         for child in value.values():
        #             if hasattr(child, 'parent'):
        #                 child.parent = self
        #     elif isinstance(value, list):
        #         for child in value:
        #             if hasattr(child, 'parent'):
        #                 child.parent = self

    def resolve_dimension(self, dim_name: str) -> int | None:
        """Resolve dimension by walking current object graph.

        This method implements lazy dimension resolution with caching. It first
        checks the cache, then walks children looking for dimension providers,
        and finally delegates to parent if not found locally.

        Parameters
        ----------
        dim_name : str
            Name of the dimension to resolve.

        Returns
        -------
        int | None
            The dimension value if found, None otherwise.

        Notes
        -----
        Resolution order:
        1. Check cache
        2. Walk fields looking for DimensionProviders
        3. Check each provider's get_dimensions()
        4. If not found, delegate to parent
        5. Cache result

        Examples
        --------
        >>> mixin = DimensionRegistryMixin()
        >>> mixin.resolve_dimension('nlay')  # doctest: +SKIP
        3
        """
        # Check cache first
        if dim_name in self._dimension_cache:
            return self._dimension_cache[dim_name]

        # Walk current children
        result = self._find_dimension_in_children(dim_name)

        if result is not None:
            self._dimension_cache[dim_name] = result
            return result

        # Delegate to parent
        if hasattr(self, "parent") and self.parent is not None:
            if hasattr(self.parent, "resolve_dimension"):
                result = self.parent.resolve_dimension(dim_name)
                if result is not None:
                    self._dimension_cache[dim_name] = result
                return result

        return None

    def _find_dimension_in_children(self, dim_name: str) -> int | None:
        """Walk fields and check dimension providers for the requested dimension.

        Parameters
        ----------
        dim_name : str
            Name of the dimension to find.

        Returns
        -------
        int | None
            The dimension value if found in any child, None otherwise.
        """
        for field_obj in attrs.fields(type(self)):
            value = getattr(self, field_obj.name, None)
            if value is None:
                continue

            # Check direct provider
            if isinstance(value, DimensionProvider):
                dims = value.get_dimensions()
                if dim_name in dims:
                    return dims[dim_name]

            # Check collections
            elif isinstance(value, dict):
                for child in value.values():
                    if isinstance(child, DimensionProvider):
                        dims = child.get_dimensions()
                        if dim_name in dims:
                            return dims[dim_name]

            elif isinstance(value, list):
                for child in value:
                    if isinstance(child, DimensionProvider):
                        dims = child.get_dimensions()
                        if dim_name in dims:
                            return dims[dim_name]

        return None

    def get_all_dimensions(self) -> dict[str, int]:
        """Get all dimensions from current children (no parent delegation).

        This method aggregates dimensions from all child DimensionProviders
        without walking up to the parent. Useful for providing dimensions
        to child components.

        Returns
        -------
        dict[str, int]
            Mapping of all dimensions provided by children.

        Examples
        --------
        >>> mixin = DimensionRegistryMixin()
        >>> mixin.get_all_dimensions()  # doctest: +SKIP
        {'nlay': 3, 'nrow': 10, 'ncol': 20}
        """
        all_dims = {}

        for field_obj in attrs.fields(type(self)):
            value = getattr(self, field_obj.name, None)
            if value is None:
                continue

            # Collect from direct providers
            if isinstance(value, DimensionProvider):
                all_dims.update(value.get_dimensions())

            # Collect from collections
            elif isinstance(value, dict):
                for child in value.values():
                    if isinstance(child, DimensionProvider):
                        all_dims.update(child.get_dimensions())

            elif isinstance(value, list):
                for child in value:
                    if isinstance(child, DimensionProvider):
                        all_dims.update(child.get_dimensions())

        return all_dims
