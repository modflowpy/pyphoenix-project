"""Write context for configuring MF6 input file writing."""

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Optional, Union

import attrs
from attrs import define, field, frozen

if TYPE_CHECKING:
    from threading import local

ArrayFormat = Literal["internal", "open/close"]
FloatPrecision = Union[int, Literal["lossless"]]

ArrayKey = Union[str, tuple[str, int], tuple[str, int, int]]
"""An array's key in `WriteContext.arrays`, relative to its component: a
field name, ``(field, kper)`` for one period of a period field (0-based,
like the field's dict keys), ``(field, layer)`` for one layer of a griddata
field (0-based), or ``(field, kper, layer)``."""


@frozen
class ArrayIO:
    """
    How to write one array. Every setting is optional, `None` meaning unset:
    a lower-ranked context's setting for the same array, or the default,
    applies instead (see `WriteContext.resolve`).

    Parameters
    ----------
    iprn : int, optional
        MF6's IPRN, the format the array is printed to the listing file in.
        Written after INTERNAL or OPEN/CLOSE; a CONSTANT array has none.
    path : Path, optional
        Write the array to this file, as OPEN/CLOSE, relative to the
        simulation directory. A layered array's whole-array path holds all
        its layers in one file; give ``(field, layer)`` entries a path each
        to write it LAYERED, a file per layer. A path outside the
        simulation directory isn't written to: the array is written beside
        its component's file instead, under the same name. Arrays sharing
        a file must hold the same values, or they're written inline.
    """

    iprn: Optional[int] = None
    path: Optional[Path] = attrs.field(default=None, converter=attrs.converters.optional(Path))

    def over(self, lower: "ArrayIO") -> "ArrayIO":
        """This entry's settings, with `lower`'s filling those it leaves unset."""
        return ArrayIO(
            **{
                a.name: _first(getattr(self, a.name), getattr(lower, a.name))
                for a in attrs.fields(ArrayIO)
            }
        )


@define
class WriteContext:
    """
    Configuration context for writing MODFLOW 6 input files.

    This class controls how simulation data is written to input files,
    including numeric precision and binary vs ASCII format.

    Can be used in three ways:
    1. Passed to write method: component.write(context=ctx)
    2. As a context manager for temporary configuration
    3. Attached to a component, as its `write_context`. Loading a
       component attaches one recording how the file wrote its arrays,
       so writing it again keeps them that way.

    Every setting is optional, `None` meaning unset. A component's write
    resolves its settings from the contexts that apply to it, highest
    first: the `write()` argument, the innermost context manager, the
    component's own `write_context`, then its ancestors'. The first that
    sets a setting wins; one no context sets gets its default. See
    `resolve`.

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
    float_precision : int or "lossless", optional
        Number of decimal places for float output, in scientific notation,
        or "lossless" (the default) to write the shortest string that
        reads back as the same value.
    array_format : ArrayFormat, optional
        How to write arrays: 'internal' inline, as INTERNAL or, for an
        array whose values are all equal, CONSTANT; 'open/close' to a
        file each, beside the component's file. If None, arrays with an
        `ArrayIO.path` are written to it, others inline. 'internal' here
        overrides paths from lower-ranked contexts, such as loaded ones;
        `use_netcdf` overrides both.
    arrays : dict, optional
        Settings for single arrays, by `ArrayKey`, relative to the
        component written.

    Examples
    --------
    >>> # Pass to write method
    >>> sim.write(context=WriteContext(float_precision=4))

    >>> # Use as context manager
    >>> with WriteContext(use_binary=True, float_precision=8):
    ...     sim.write()

    >>> # Print one array to the listing file
    >>> npf.write_context = WriteContext(arrays={"k": ArrayIO(iprn=1)})
    """

    use_binary: Optional[bool] = field(default=None)
    use_netcdf: Optional[bool] = field(default=None)
    binary_threshold: Optional[int] = field(default=None)
    float_precision: Optional[FloatPrecision] = field(default=None)
    array_format: Optional[ArrayFormat] = field(default=None)
    arrays: dict[ArrayKey, ArrayIO] = field(factory=dict)

    # Class-level thread-local storage for context stack
    _global_context_stack: ClassVar["local"]

    _DEFAULTS: ClassVar[dict[str, Any]] = {
        "use_binary": False,
        "use_netcdf": False,
        "float_precision": "lossless",
    }

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

        Returns the most recently entered context manager, or an empty
        context (every setting unset) if no context manager is active.

        Returns
        -------
        WriteContext
            The active context, or an empty one.
        """
        # Create a class-level thread-local if it doesn't exist
        if not hasattr(cls, "_global_context_stack"):
            cls._global_context_stack = threading.local()

        if hasattr(cls._global_context_stack, "stack") and cls._global_context_stack.stack:
            return cls._global_context_stack.stack[-1]
        return cls()

    @classmethod
    def default(cls) -> "WriteContext":
        """
        Create a WriteContext with default settings.

        Returns
        -------
        WriteContext
            A context with every setting at its default value.
        """
        return cls.resolve()

    @classmethod
    def resolve(cls, *contexts: "WriteContext | None") -> "WriteContext":
        """
        Merge `contexts`, highest-ranked first, into one context, filling
        any setting none of them sets with its default. `None`s are
        skipped.

        A setting is taken from the highest context that sets it. Entries
        for one array from several contexts merge setting by setting.
        """
        merged = cls()
        for ctx in contexts:
            if ctx is not None:
                merged = merged.over(ctx)
        return attrs.evolve(
            merged,
            **{k: v for k, v in cls._DEFAULTS.items() if getattr(merged, k) is None},
        )

    def over(self, lower: "WriteContext") -> "WriteContext":
        """This context's settings, with `lower`'s filling those it leaves unset."""
        values = {
            a.name: _first(getattr(self, a.name), getattr(lower, a.name))
            for a in attrs.fields(WriteContext)
            if a.name != "arrays"
        }
        arrays = dict(lower.arrays)
        if self.array_format == "internal":
            # inline beats the lower contexts' files
            arrays = {k: attrs.evolve(io, path=None) for k, io in arrays.items()}
        for key, io in self.arrays.items():
            arrays[key] = io.over(arrays[key]) if key in arrays else io
        return WriteContext(**values, arrays=arrays)

    def array_io(self, *key: Any) -> ArrayIO:
        """The settings for the array at `key` (see `ArrayKey`), merged from
        its own entry and those of the arrays containing it: a layer of a
        period's array falls back to the period's entry, then the field's."""
        io = ArrayIO()
        for n in range(len(key), 0, -1):
            entry = self.arrays.get(key[0] if n == 1 else key[:n])
            if entry is not None:
                io = io.over(entry)
        return io

    def to_numpy_printoptions(self) -> dict:
        """
        Convert WriteContext settings to numpy printoptions dict.

        Returns
        -------
        dict
            Dictionary suitable for use with np.printoptions()
        """
        import sys

        options: dict[str, int | str] = {"linewidth": sys.maxsize, "threshold": sys.maxsize}
        if self.float_precision is None or self.float_precision == "lossless":
            options["floatmode"] = "unique"
        else:
            options["precision"] = self.float_precision
        return options


def _first(*values: Any) -> Any:
    """The first of `values` that isn't None, or None."""
    return next((v for v in values if v is not None), None)
