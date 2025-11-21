"""
Context to register dimension sizes during load-time component structuring.
"""

from contextvars import ContextVar, Token
from typing import ContextManager

_dim_context: ContextVar[dict[str, int]] = ContextVar("structuring_dims", default={})


class DimContext(ContextManager):
    """
    Context for storing dimension values during component initialization.

    Provides dimensions to array converters during component construction.
    Avoids having to pass dimensions explicitly through every constructor
    or construct components in a specific order. Supports nested contexts
    that automatically merge dimensions from parent and child components.

    Parameters
    ----------
    dims : dict[str, int]
        Dimension name to value mapping.

    Examples
    --------
    If an array field's dimensions match those in the context,
    the converter can broadcast a scalar to a full array.
    >>> with DimContext({'nlay': 3, 'nrow': 10, 'ncol': 20}):
    ...     ic = Ic(strt=1.0)  # broadcast to (nlay, nrow, ncol)

    Nested contexts merge dimensions. In the following example,
    the head array converter is broadcast to (nper, nlay) with
    nper from the outer context and nlay from the inner.
    >>> with DimContext({'nper': 10}):  # simulation scope
    ...     with DimContext({'nlay': 3, 'nodes': 300}):  # model scope
    ...         chd = Chd(head={0: {0: 1.0}})  # broadcast to (nper, nlay)
    """

    def __init__(self, dims: dict[str, int]):
        self.dims = dims
        self.token: Token | None = None

    def __enter__(self) -> "DimContext":
        """Enter context manager, merging dims with current context."""
        current = _dim_context.get().copy()
        current.update(self.dims)
        self.token = _dim_context.set(current)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager, restoring previous dimension context."""
        if self.token is not None:
            _dim_context.reset(self.token)
        # Don't suppress exceptions
        return None

    @classmethod
    def current(cls) -> dict[str, int]:
        """
        Get the currently active dimension context.

        Returns the merged dimensions from all active contexts, or an empty
        dict if no context is active.

        Returns
        -------
        dict[str, int]
            The active dimension mapping.
        """
        return _dim_context.get()
