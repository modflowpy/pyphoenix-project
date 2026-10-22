"""flopy3's constructor keywords, accepted with a deprecation warning.

flopy3 names a package's period list after its v1 DFN field (LAK's
`perioddata`, LKT's `lakeperioddata`, ...), and spreads STO's and OC's
over several keywords whose values are shaped differently. flopy4 calls
each of them `stress_period_data`. A generated class lists flopy3's names
in `legacy_kwargs`, and `LegacyKwargs` translates them when the class is
called, before attrs' `__init__` sees them.
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


class LegacyKwargs(ABCMeta):
    """Translate a class's `legacy_kwargs` when it's called."""

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
