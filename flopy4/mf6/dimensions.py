"""Dimension resolution in MF6 components"""

from typing import Protocol, runtime_checkable

import attrs
from attrs import field
from xattree import xattree


@runtime_checkable
class DimensionProvider(Protocol):
    """
    Implement this protocol to participate in dimension resolution
    as a provider.

    For components that provide dimensions to consuming components.

    A component implementing this declares named dimension sizes.
    Its consumers resolve dimensions by walking the object graph.
    """

    def get_dimensions(self) -> dict[str, int]:
        """
        Return dimension sizes.

        Includes both explicit dimensions (field defined on the component)
        and computed dimensions (calculated from other values).

        Returns
        -------
        dict[str, int]
            Map of dimension names to their integer sizes.

        Examples
        --------
        >>> dis = Dis(nlay=3, nrow=10, ncol=20)
        >>> dis.get_dimensions()
        {'nlay': 3, 'nrow': 10, 'ncol': 20, 'nodes': 600, 'ncpl': 200}
        """
        ...


class DimensionRegistry(Protocol):
    """
    Implement this protocol to participate in dimension resolution
    as a consumer.

    For components that consume dimensions from provider components.
    """

    def resolve_dimension(self, dim_name: str) -> int | None:
        """
        Resolve dimension by lazily walking the object graph.

        Walk the current component's children looking for dimension
        providers. Dimensions not found are sought in the parent.
        Results are cached after first access.

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
        2. Walk child fields/collections
        3. If not found, check parent
        4. Cache result

        Examples
        --------
        >>> gwf = Gwf(dis=Dis(nlay=3, nrow=10, ncol=20))
        >>> gwf.resolve_dimension('nlay')
        3
        >>> gwf.resolve_dimension('nonexistent')
        None
        """
        ...

    def get_all_dimensions(self) -> dict[str, int]:
        """
        Get all dimensions.

        Returns
        -------
        dict[str, int]
            Mapping of all dimensions

        Examples
        --------
        >>> gwf = Gwf(dis=Dis(nlay=3, nrow=10, ncol=20))
        >>> gwf.get_all_dimensions()
        {'nlay': 3, 'nrow': 10, 'ncol': 20, 'nodes': 600, 'ncpl': 200}
        """
        ...


@xattree
class DimensionRegistryMixin:
    """
    Mixin for components which consume dimensions from providers.

    This mixin adds dimension resolution capabilities to attrs classes. It provides
    lazy, cached dimension resolution, walking the tree to find dimension providers.

    The mixin uses @xattree (same as Component) for compatibility. Using attrs.field
    for _dimension_cache signals to xattree to treat it as a regular field without
    special xattree handling.

    Attributes
    ----------
    _dimension_cache : dict[str, int]
        Cache of resolved dimensions

    Notes
    -----
    During xattree coexistence, the _set_child_parents() method is a no-op
    since xattree already manages parent references. This will be enabled
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
        """
        Resolve dimension by walking current object graph.

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
        result = self._dimension_cache.get(dim_name)
        if result is not None:
            return result

        result = self._find_dimension_in_children(dim_name)
        if result is not None:
            self._dimension_cache[dim_name] = result
            return result

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
        for field_obj in attrs.fields(type(self)):  # type: ignore[arg-type]
            if (value := getattr(self, field_obj.name, None)) is None:
                continue
            if isinstance(value, DimensionProvider):
                dims = value.get_dimensions()
                if dim_name in dims:
                    return dims[dim_name]
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
        """
        Get all dimensions.

        Returns
        -------
        dict[str, int]
            Mapping of all dimensions

        Examples
        --------
        >>> mixin = DimensionRegistryMixin()
        >>> mixin.get_all_dimensions()  # doctest: +SKIP
        {'nlay': 3, 'nrow': 10, 'ncol': 20}
        """
        dims = {}

        for field_obj in attrs.fields(type(self)):  # type: ignore[arg-type]
            if (value := getattr(self, field_obj.name, None)) is None:
                continue
            if isinstance(value, DimensionProvider):
                dims.update(value.get_dimensions())
            elif isinstance(value, dict):
                for child in value.values():
                    if isinstance(child, DimensionProvider):
                        dims.update(child.get_dimensions())
            elif isinstance(value, list):
                for child in value:
                    if isinstance(child, DimensionProvider):
                        dims.update(child.get_dimensions())

        return dims
