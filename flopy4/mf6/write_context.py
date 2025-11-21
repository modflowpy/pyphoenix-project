"""
Write context for configuring MF6 input file writing.

Uses contextvars for async-safe context management. The context stack
is maintained per async context, allowing WriteContext to work correctly
with asyncio and concurrent code.
"""

from contextvars import ContextVar
from typing import Literal, Optional

from attrs import define, field

ArrayFormat = Literal["internal", "constant", "open/close"]

_write_context_stack: ContextVar[list["WriteContext"]] = ContextVar(
    "write_context_stack", default=[]
)


@define
class WriteContext:
    """
    Configuration context for writing MODFLOW 6 input files.

    This class controls how simulation data is written to input files,
    including numeric precision, binary vs ASCII format, and path handling.

    Can be used in two ways:
    1. Passed to write method: component.write(context=ctx)
    2. As a context manager for temporary configuration

    Parameters
    ----------
    use_binary : bool, optional
        Prefer binary files for arrays. Default is False.
    use_netcdf : bool, optional
        Prefer netcdf files for arrays. Default is False.
    binary_threshold : int, optional
        Size threshold (in bytes) for using binary format.
        Arrays larger than this will be written as binary.
        If None, use_binary setting is used unconditionally.
    float_precision : int, optional
        Number of decimal places for float output. Default is 8.
    use_relative_paths : bool, optional
        Use relative paths in input files. Default is True.
    array_format : ArrayFormat, optional
        How to write array data: 'internal', 'constant', or 'open/close'.
        If None, automatically determined based on array properties.

    Examples
    --------
    >>> # Pass to write method
    >>> sim.write(context=WriteContext(float_precision=4))

    >>> # Use as context manager
    >>> with WriteContext(use_binary=True, float_precision=8):
    ...     sim.write()
    """

    use_binary: bool = field(default=False)
    use_netcdf: bool = field(default=False)
    binary_threshold: Optional[int] = field(default=None)
    float_precision: int = field(default=8)
    use_relative_paths: bool = field(default=True)
    array_format: Optional[ArrayFormat] = field(default=None)

    def __enter__(self) -> "WriteContext":
        """Enter context manager, pushing this context onto the stack."""
        # Get current stack and append this context
        stack = _write_context_stack.get().copy()
        stack.append(self)
        _write_context_stack.set(stack)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager, popping this context from the stack."""
        stack = _write_context_stack.get().copy()
        if stack:
            stack.pop()
            _write_context_stack.set(stack)
        # Don't suppress exceptions
        return None

    @classmethod
    def current(cls) -> "WriteContext":
        """
        Get the currently active WriteContext from the context stack.

        Returns the most recently entered context manager, or a default
        context if no context manager is active.

        Returns
        -------
        WriteContext
            The active context, or a default context.
        """
        stack = _write_context_stack.get()
        if stack:
            return stack[-1]
        return cls.default()

    @classmethod
    def default(cls) -> "WriteContext":
        """
        Create a WriteContext with default settings.

        Returns
        -------
        WriteContext
            A context with default configuration values.
        """
        return cls()

    def to_numpy_printoptions(self) -> dict:
        """
        Convert WriteContext settings to numpy printoptions dict.

        Returns
        -------
        dict
            Dictionary suitable for use with np.printoptions()
        """
        import sys

        return {
            "precision": self.float_precision,
            "linewidth": sys.maxsize,
            "threshold": sys.maxsize,
        }

    def get_float_format(self) -> str:
        """
        Get the float format string based on precision setting.

        Returns
        -------
        str
            Format string for floating point numbers (e.g., "%.6e")
        """
        return f"%.{self.float_precision}e"
