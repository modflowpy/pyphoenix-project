"""Protocols for dimension resolution in MF6 components.

This module defines structural protocols that components can implement
to participate in the dimension resolution system.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class DimensionProvider(Protocol):
    """Components that provide dimensions to consumers.

    Components implementing this protocol declare what dimensions they provide
    and their current values. This is the single source of truth for dimension
    values in the object graph.
    """

    def get_dimensions(self) -> dict[str, int]:
        """Return all dimensions this component provides.

        This method should return both explicit dimensions (fields defined on the
        component) and computed dimensions (calculated from other values).

        Returns
        -------
        dict[str, int]
            Mapping of dimension names to their integer values.

        Examples
        --------
        >>> dis = Dis(nlay=3, nrow=10, ncol=20)
        >>> dis.get_dimensions()
        {'nlay': 3, 'nrow': 10, 'ncol': 20, 'nodes': 600, 'ncpl': 200}
        """
        ...


class DimensionRegistry(Protocol):
    """Containers that resolve dimensions from child providers.

    Components implementing this protocol can walk their object graph to find
    dimension providers and resolve dimension values on demand.
    """

    def resolve_dimension(self, dim_name: str) -> int | None:
        """Resolve dimension by lazily walking object graph.

        Resolution walks the current component's children looking for dimension
        providers. If the dimension is not found locally, resolution delegates
        to the parent. Results are cached for performance.

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
        2. Walk child fields/collections for DimensionProviders
        3. If not found, delegate to parent
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
        """Get all dimensions from current children (no parent delegation).

        This method aggregates dimensions from all child DimensionProviders
        without walking up to the parent. Useful for providing dimensions
        to child components.

        Returns
        -------
        dict[str, int]
            Mapping of all dimensions provided by children.

        Notes
        -----
        This method does not delegate to parent - it only collects dimensions
        from the current component's immediate children.

        Examples
        --------
        >>> gwf = Gwf(dis=Dis(nlay=3, nrow=10, ncol=20))
        >>> gwf.get_all_dimensions()
        {'nlay': 3, 'nrow': 10, 'ncol': 20, 'nodes': 600, 'ncpl': 200}
        """
        ...
