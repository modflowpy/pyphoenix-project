"""flopy3's constructor keywords and attributes, with a deprecation warning.

flopy3 names some packages' period list after its v1 DFN field (LAK's
`perioddata`, LKT's `lakeperioddata`, ...), and spreads STO's and OC's over
several keywords whose values are shaped differently. flopy4 calls each of
them `stress_period_data`. A generated class lists flopy3's names in
`legacy_kwargs`, and `LegacyKwargs` translates them when the class is
called, before attrs' `__init__` sees them.

The same names work as attributes, by name only: `lak.perioddata` is
`lak.stress_period_data`, not flopy3's `MFTransientList`. A keyword that's
converted has no value of its own to read or assign, so its attribute raises
instead.
"""

import warnings
from abc import ABCMeta
from collections.abc import Callable, Mapping
from typing import Any, NamedTuple


class Legacy(NamedTuple):
    """A flopy3 constructor keyword: the keyword flopy4 takes instead, and
    the function converting its value, if it's shaped differently.

    Keywords converting to the same flopy4 keyword are converted together:
    the function takes each one given, as a keyword argument, and returns
    the flopy4 value. Without a function, the value passes unchanged.
    """

    name: str
    convert: Callable[..., Any] | None = None


class _LegacyAttribute:
    """A class's attribute for a `legacy_kwargs` keyword."""

    def __init__(self, old: str, new: Legacy) -> None:
        self.old = old
        self.new = new

    def _name(self, obj: Any, stacklevel: int) -> str:
        cls_name = type(obj).__name__
        if self.new.convert is not None:
            # an AttributeError, so hasattr() is False
            raise AttributeError(
                f"{cls_name}.{self.old} is gone: flopy4 keeps it in {self.new.name}, "
                "shaped differently. See docs/migrating.md."
            )
        warnings.warn(
            f"{cls_name}.{self.old} is deprecated; use {self.new.name}",
            DeprecationWarning,
            stacklevel=stacklevel,
        )
        return self.new.name

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        return self if obj is None else getattr(obj, self._name(obj, stacklevel=3))

    def __set__(self, obj: Any, value: Any) -> None:
        # one more than __get__, for attrs' generated __setattr__
        setattr(obj, self._name(obj, stacklevel=4), value)


class LegacyKwargs(ABCMeta):
    """Translate a class's `legacy_kwargs` when it's called, and give it an
    attribute for each."""

    def __init__(cls, name: str, bases: tuple, namespace: dict, **kwargs: Any) -> None:
        super().__init__(name, bases, namespace, **kwargs)
        for old, new in namespace.get("legacy_kwargs", {}).items():
            setattr(cls, old, _LegacyAttribute(old, new))

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        legacy = getattr(cls, "legacy_kwargs", None)
        if legacy and not kwargs.keys().isdisjoint(legacy):
            kwargs = _translate(cls.__name__, legacy, kwargs)
        return super().__call__(*args, **kwargs)


def _translate(cls_name: str, legacy: Mapping[str, Legacy], kwargs: dict) -> dict:
    groups: dict[Legacy, dict[str, Any]] = {}
    for old, new in legacy.items():
        if old in kwargs:
            groups.setdefault(new, {})[old] = kwargs.pop(old)
    for new, given in groups.items():
        olds = ", ".join(f"{old}=..." for old in given)
        if new.name in kwargs:
            raise TypeError(f"{cls_name}() got both {olds} and {new.name}=...")
        warnings.warn(
            f"{cls_name}({olds}) is deprecated; use {new.name}=...",
            DeprecationWarning,
            # the caller of LegacyKwargs.__call__
            stacklevel=3,
        )
        if new.convert is not None:
            kwargs[new.name] = new.convert(**given)
        else:
            (kwargs[new.name],) = given.values()
    return kwargs


def _periods(value: Any) -> dict[int, Any]:
    """flopy3's period-keyed value, as a dict: a dict is keyed by period
    already, anything else applies to period 0."""
    return dict(value) if isinstance(value, Mapping) else {0: value}


def sto_period_data(steady_state: Any = None, transient: Any = None) -> dict[int, list]:
    """STO's `stress_period_data` from flopy3's `steady_state` and
    `transient`. Each is `{kper: True}`, `True` (period 0), or a list of
    periods. A period can't be both."""

    def periods(value: Any) -> list[int]:
        if value is None:
            return []
        if isinstance(value, bool):
            return [0] if value else []
        if isinstance(value, Mapping):
            return [kper for kper, on in value.items() if on]
        return list(value)

    data: dict[int, list] = {}
    for word, value in (("STEADY-STATE", steady_state), ("TRANSIENT", transient)):
        for kper in periods(value):
            if kper in data:
                raise ValueError(f"period {kper} is both steady-state and transient")
            data[kper] = [(word,)]
    return dict(sorted(data.items()))


def oc_period_data(saverecord: Any = None, printrecord: Any = None) -> dict[int, list]:
    """OC's `stress_period_data` from flopy3's `saverecord` and
    `printrecord`. Each is a list of `(rtype, ocsetting...)` tuples for
    period 0, or a dict of them by period. Each period's saves come
    before its prints, as flopy3 writes them."""
    data: dict[int, list] = {}
    for word, value in (("SAVE", saverecord), ("PRINT", printrecord)):
        if value is None:
            continue
        for kper, records in _periods(value).items():
            # a single (rtype, ocsetting...) tuple
            if records and isinstance(records[0], str):
                records = [records]
            data.setdefault(kper, []).extend((word, *record) for record in records)
    return dict(sorted(data.items()))
