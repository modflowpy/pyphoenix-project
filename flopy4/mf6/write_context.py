"""Write context for configuring MF6 input file writing."""

import hashlib
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Optional, Union

import attrs
import numpy as np
from attrs import define, field, frozen

if TYPE_CHECKING:
    from threading import local

ArrayFormat = Literal["constant", "internal", "open/close", "binary"]
"""The control record to write an array with: CONSTANT, INTERNAL,
OPEN/CLOSE, or OPEN/CLOSE (BINARY). "constant" falls back to INTERNAL for
an array whose values aren't all equal. Unset, the writer chooses: a file
for an array with an `ArrayIO.path`, else CONSTANT or INTERNAL."""

INLINE_FORMATS = ("constant", "internal")
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
        The array's file, relative to the simulation directory, for a
        `format` of "open/close" (implied by a path without a format) or
        "binary". Without one, a file is named for the component and
        field, beside the component's file. A path outside the simulation
        directory isn't written to: the array is written beside its
        component's file instead, under the same name. Arrays sharing a
        file must hold the same values, or they're written inline.
    format : ArrayFormat, optional
        The control record to write the array with. Overrides the
        context's `array_format`. A ``(field, layer)`` entry's is for
        that layer's record, when the array is written LAYERED.
    layered : bool, optional
        Whether to write a layered array LAYERED, a record per layer, or
        as one record. Unset, the writer chooses: one CONSTANT record if
        every value is equal, else LAYERED.
    hash : str, optional
        The array's values' `array_hash` when loaded from its file. When
        arrays sharing a file disagree at write time, those whose values
        still match their hash keep the file and the others are written
        inline. Set by loading; not compared by `==`.

    Loading sets each array's `format` and `layered` to the control
    records it was read from, so writing it again writes them back.
    """

    iprn: Optional[int] = None
    path: Optional[Path] = attrs.field(default=None, converter=attrs.converters.optional(Path))
    format: Optional[ArrayFormat] = None
    layered: Optional[bool] = None
    hash: Optional[str] = attrs.field(default=None, eq=False, repr=False)

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
    use_netcdf : bool, optional
        Prefer netcdf files for arrays. Default is False.
    binary_threshold : int, optional
        With an `array_format` of "binary", write only arrays (or layers,
        for a file per layer) bigger than this many bytes as binary: 8 per
        value of a real array, 4 of an integer one. Others are written as
        if `array_format` were unset. If None, every array is.
    float_precision : int or "lossless", optional
        Number of decimal places for float output, in scientific notation,
        or "lossless" (the default) to write the shortest string that
        reads back as the same value.
    array_format : ArrayFormat, optional
        The control record to write arrays with, unless an array's own
        `ArrayIO.format` in this context says otherwise. "open/close" and
        "binary" write each array to a file (a layered array's a file per
        layer), its `ArrayIO.path` or one named for its component and
        field. Set here, it overrides lower-ranked contexts' formats, such
        as loaded ones, and, if "constant" or "internal", their paths; an
        `ArrayIO.path` of this context still writes its array to the file.
        `use_netcdf` overrides it.
    strict : bool, optional
        Raise instead of warning when the arrays' files can't be written
        as given: a file outside the simulation directory, or arrays that
        share a file and disagree. Raises before the component writes any
        array file. Default is False.
    arrays : dict, optional
        Settings for single arrays, by `ArrayKey`, relative to the
        component written.

    Examples
    --------
    >>> # Pass to write method
    >>> sim.write(context=WriteContext(float_precision=4))

    >>> # Use as context manager
    >>> with WriteContext(array_format="binary", float_precision=8):
    ...     sim.write()

    >>> # Print one array to the listing file
    >>> npf.write_context = WriteContext(arrays={"k": ArrayIO(iprn=1)})
    """

    use_netcdf: Optional[bool] = field(default=None)
    binary_threshold: Optional[int] = field(default=None)
    float_precision: Optional[FloatPrecision] = field(default=None)
    array_format: Optional[ArrayFormat] = field(default=None)
    strict: Optional[bool] = field(default=None)
    arrays: dict[ArrayKey, ArrayIO] = field(factory=dict)

    # Class-level thread-local storage for context stack
    _global_context_stack: ClassVar["local"]

    _DEFAULTS: ClassVar[dict[str, Any]] = {
        "use_netcdf": False,
        "float_precision": "lossless",
        "strict": False,
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
        if self.array_format is not None:
            # this format beats the lower contexts', and inline their files
            cleared: dict[str, Any] = {"format": None}
            if self.array_format in INLINE_FORMATS:
                cleared["path"] = None
            arrays = {k: attrs.evolve(io, **cleared) for k, io in arrays.items()}
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


def array_hash(values: Any) -> str:
    """A digest of an array's values, as written: integers as 8-byte, any
    other number as an 8-byte float, in C order. See `ArrayIO.hash`."""
    values = np.asarray(values)
    dtype = "<i8" if np.issubdtype(values.dtype, np.integer) else "<f8"
    data = np.ascontiguousarray(values, dtype=dtype).tobytes()
    return hashlib.blake2b(data, digest_size=16).hexdigest()


def _first(*values: Any) -> Any:
    """The first of `values` that isn't None, or None."""
    return next((v for v in values if v is not None), None)
