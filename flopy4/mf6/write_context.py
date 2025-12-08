"""Write context for configuring MF6 input file writing."""

import threading
from typing import TYPE_CHECKING, ClassVar, Literal, Optional

from attrs import define, field

if TYPE_CHECKING:
    from threading import local

ArrayFormat = Literal["internal", "constant", "open/close"]


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

    # Class-level thread-local storage for context stack
    _global_context_stack: ClassVar["local"]

    def __enter__(self) -> "WriteContext":
        """Enter context manager, pushing this context onto the stack."""
        # Use class-level thread-local storage
        if not hasattr(WriteContext, "_global_context_stack"):
            WriteContext._global_context_stack = threading.local()
        if not hasattr(WriteContext._global_context_stack, "stack"):
            WriteContext._global_context_stack.stack = []
        WriteContext._global_context_stack.stack.append(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager, popping this context from the stack."""
        if (
            hasattr(WriteContext, "_global_context_stack")
            and hasattr(WriteContext._global_context_stack, "stack")
            and WriteContext._global_context_stack.stack
        ):
            WriteContext._global_context_stack.stack.pop()

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
        # Create a class-level thread-local if it doesn't exist
        if not hasattr(cls, "_global_context_stack"):
            cls._global_context_stack = threading.local()

        if hasattr(cls._global_context_stack, "stack") and cls._global_context_stack.stack:
            return cls._global_context_stack.stack[-1]
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
