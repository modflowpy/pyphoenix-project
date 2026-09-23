"""Dimension resolution in MF6 components"""

from typing import Protocol, runtime_checkable

from pydantic.dataclasses import is_pydantic_dataclass


@runtime_checkable
class DimensionProvider(Protocol):
    """
    Implement this protocol to participate in dimension resolution
    as a provider.

    For components that provide dimensions to consuming components.

    A component implementing this declares named dimension sizes.
    Its consumers resolve dimensions by walking the object graph.
    """

    def get_dims(self) -> dict[str, int]:
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
        >>> dis.get_dims()
        {'nlay': 3, 'nrow': 10, 'ncol': 20, 'nodes': 600, 'ncpl': 200}
        """
        ...


@runtime_checkable
class DimensionResolver(Protocol):
    """
    Implement this protocol to participate in dimension resolution
    as a consumer.

    For components that consume dimensions from provider components.
    """

    def resolve_dims(self, *dims: str) -> dict[str, int]:
        """
        Resolve one or more dimensions by walking the object graph.

        Walk the current component's children looking for dimension
        providers. Dimensions not found are sought in the parent.
        Results are cached after first access.

        Parameters
        ----------
        *dims : str
            Dimension names to resolve. If not provided, resolves all
            available dimensions.

        Returns
        -------
        dict[str, int]
            Dictionary mapping dimension names to their values. Only includes
            dimensions that were found (requested dims that don't exist are omitted).

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
        >>> gwf.resolve_dims()
        {'nlay': 3, 'nrow': 10, 'ncol': 20, 'nodes': 600, 'ncpl': 200}
        >>> gwf.resolve_dims('nlay')
        {'nlay': 3}
        >>> gwf.resolve_dims('nlay', 'nrow')
        {'nlay': 3, 'nrow': 10}
        >>> gwf.resolve_dims('nonexistent')
        {}
        """
        ...


class DimensionResolverMixin:
    """
    Mixin for components which consume dimensions from providers.

    Attributes
    ----------
    _dimension_cache : dict[str, int]
        Cache of resolved dimensions (stored as instance variable, not attrs field)
    """

    @property
    def _dimension_cache(self) -> dict:
        # Lazily initialize in __dict__ directly rather than as a real attrs
        # field: avoids needing a mutable-default Factory, and doesn't
        # depend on __attrs_post_init__ chaining order across mixins.
        if "_dimension_cache" not in self.__dict__:
            self.__dict__["_dimension_cache"] = {}
        return self.__dict__["_dimension_cache"]

    def __post_init__(self) -> None:
        if hasattr(super(), "__post_init__"):
            super().__post_init__()  # type: ignore[misc]

    def resolve_dims(self, *dims: str) -> dict[str, int]:
        """
        Resolve one or more dimensions by walking the object graph.

        This method implements lazy dimension resolution with caching. It first
        checks the cache, then walks children looking for dimension providers,
        and finally delegates to parent if not found locally.

        Parameters
        ----------
        *dims : str
            Dimension names to resolve. If not provided, resolves all
            available dimensions.

        Returns
        -------
        dict[str, int]
            Dictionary mapping dimension names to their values. Only includes
            dimensions that were found (requested dims that don't exist are omitted).

        Notes
        -----
        Resolution order:
        1. Check cache
        2. Walk fields looking for DimensionProviders
        3. Check each provider's dims()
        4. If not found, delegate to parent
        5. Cache result

        Examples
        --------
        >>> mixin = DimensionResolverMixin()
        >>> mixin.resolve_dims()  # doctest: +SKIP
        {'nlay': 3, 'nrow': 10, 'ncol': 20}
        >>> mixin.resolve_dims('nlay')  # doctest: +SKIP
        {'nlay': 3}
        >>> mixin.resolve_dims('nlay', 'nrow')  # doctest: +SKIP
        {'nlay': 3, 'nrow': 10}
        """
        # No args: return all dimensions
        if not dims:
            return self._get_all_dimensions()

        # One or more args: return dict of found dimensions
        result_dict = {}
        for dim_name in dims:
            # Check cache
            if dim_name in self._dimension_cache:
                result_dict[dim_name] = self._dimension_cache[dim_name]
                continue

            # Find in children
            value = self._find_dimension_in_children(dim_name)
            if value is not None:
                self._dimension_cache[dim_name] = value
                result_dict[dim_name] = value
                continue

            # Check parent
            if hasattr(self, "_parent") and self._parent is not None:
                if hasattr(self._parent, "resolve_dims"):
                    parent_result = self._parent.resolve_dims(dim_name)
                    if dim_name in parent_result:
                        value = parent_result[dim_name]
                        self._dimension_cache[dim_name] = value
                        result_dict[dim_name] = value

        return result_dict

    def _find_dimension_in_children(self, dim_name: str) -> int | None:
        """Walk fields and check dimension providers for the requested dimension."""
        for _source, provider_dims in self._walk_providers():
            if dim_name in provider_dims:
                return provider_dims[dim_name]
        return None

    def _walk_providers(self):
        """Yield (source_label, dims_dict) for each DimensionProvider in child fields."""
        for name in type(self).__pydantic_fields__:  # type: ignore[attr-defined]
            if (value := getattr(self, name, None)) is None:
                continue
            if isinstance(value, DimensionProvider):
                yield name, value.get_dims()
            elif isinstance(value, dict):
                for child_key, child in value.items():
                    if isinstance(child, DimensionProvider):
                        yield f"{name}[{child_key}]", child.get_dims()
            elif isinstance(value, list):
                for idx, child in enumerate(value):
                    if isinstance(child, DimensionProvider):
                        yield f"{name}[{idx}]", child.get_dims()

    def _get_all_dimensions(self) -> dict[str, int]:
        """Get all dimensions from children and parent. Children take precedence."""
        resolved_dims = {}
        dim_sources: dict[str, str] = {}

        # Parent dims (lower priority)
        if hasattr(self, "_parent") and self._parent is not None:
            if hasattr(self._parent, "resolve_dims"):
                parent_dims = self._parent.resolve_dims()
                resolved_dims.update(parent_dims)
                for dim_name in parent_dims:
                    dim_sources[dim_name] = "parent"

        # Child dims (override parent, conflict with each other)
        child_dims: dict[str, int] = {}
        for source, provider_dims in self._walk_providers():
            conflicts = set(provider_dims.keys()) & set(child_dims.keys())
            if conflicts:
                conflict_sources = {
                    dim: dim_sources[dim] for dim in conflicts if dim_sources[dim] != "parent"
                }
                raise ValueError(
                    f"{type(self).__name__} has multiple providers "
                    f"for dimensions: {conflicts}.\n"
                    f"'{source}' provides {set(provider_dims.keys())}, "
                    f"already provided by {conflict_sources}"
                )
            child_dims.update(provider_dims)
            resolved_dims.update(provider_dims)
            for dim_name in provider_dims:
                dim_sources[dim_name] = source

        return resolved_dims


def validate_dimension_resolution(component) -> list[str]:
    """
    Validate that all array fields can resolve their required dimensions.

    This function walks the component hierarchy and checks that every array field
    with dimension requirements can resolve those dimensions from the parent chain.
    Use this in tests or CI to catch missing dimension providers.

    Parameters
    ----------
    component : Component
        The component to validate (must have DimensionResolver interface)

    Returns
    -------
    list[str]
        List of error messages for dimensions that cannot be resolved.
        Empty list means all dimensions can be resolved successfully.

    Examples
    --------
    >>> errors = validate_dimension_resolution(simulation)
    >>> if errors:
    ...     for error in errors:
    ...         print(error)
    >>> # Use in tests:
    >>> assert not validate_dimension_resolution(sim), "Dimension resolution failed"
    """
    errors = []

    # Check all array fields on this component
    for name, finfo in type(component).__pydantic_fields__.items():
        # Check if field has dimension metadata
        meta = finfo.json_schema_extra or {}
        if isinstance(meta, dict) and "dims" in meta:
            dims_needed = meta["dims"]
            # Check if this component has a parent and can resolve dimensions
            if hasattr(component, "_parent") and component._parent:
                if hasattr(component._parent, "resolve_dims"):
                    for dim in dims_needed:
                        result = component._parent.resolve_dims(dim)
                        if dim not in result:
                            errors.append(
                                f"{type(component).__name__}.{name} needs dimension '{dim}' "
                                f"but it's not available in parent hierarchy"
                            )

    # Recursively validate children
    for name in type(component).__pydantic_fields__:
        value = getattr(component, name, None)
        if value is None:
            continue

        # Check if child is a pydantic dataclass instance
        if is_pydantic_dataclass(type(value)):
            errors.extend(validate_dimension_resolution(value))
        elif isinstance(value, dict):
            for child in value.values():
                if is_pydantic_dataclass(type(child)):
                    errors.extend(validate_dimension_resolution(child))
        elif isinstance(value, list):
            for child in value:
                if is_pydantic_dataclass(type(child)):
                    errors.extend(validate_dimension_resolution(child))

    return errors
