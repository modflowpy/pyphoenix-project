"""Schema types for codegen v2 recarray block columns."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class Column:
    """Descriptor for one column in a recarray block schema.

    Parameters
    ----------
    name:
        Column name — matches the recarray dtype field name and the MF6 token.
    role:
        Parsing/serialization role.  One of:
        ``"cellid"``, ``"feature_id"``, ``"value"``, ``"boundname"``,
        ``"keystring"``, ``"keystring_value"``, ``"inline_keyword"``.
    dfn_type:
        MF6 DFN type string (``"double"``, ``"integer"``, ``"string"``,
        ``"keyword"``, ``"object"``).  Defaults to ``"double"``.
    optional:
        True when the column is absent from the recarray dtype unless
        ``boundnames=True`` or ``auxiliary`` is set.
    shape:
        DFN shape string (e.g. ``"ncelldim"``); used for cellid columns.
    time_series:
        When True the column stores either a float or a time-series name
        string and is always ``np.object_`` dtype.
    dtype:
        Explicit numpy dtype override string (e.g. ``"np.object_"``).
        When set, takes precedence over the ``dfn_type`` lookup.
    prefix:
        Fixed MF6 token(s) written before the value (e.g. ``"TAB6 FILEIN"``).
    """

    name: str
    role: str
    dfn_type: str = "double"
    optional: bool = False
    shape: str | None = None
    time_series: bool = False
    dtype: str | None = None
    prefix: str | None = None


class Schema:
    """Base class for recarray block schemas with named Column attributes.

    Subclasses declare Column instances as class attributes; ``columns()``
    returns them in declaration order.

    Example
    -------
    ::

        class _PeriodSchema(Schema):
            cellid    = Column("cellid",    role="cellid",    dfn_type="integer", shape="ncelldim")
            head      = Column("head",      role="value",     dfn_type="double",  time_series=True)
            boundname = Column("boundname", role="boundname", dfn_type="string",  optional=True)

        __period_schema__: ClassVar[type[Schema]] = _PeriodSchema
    """

    @classmethod
    def columns(cls) -> list[Column]:
        """Return all Column attributes in class-body declaration order."""
        return [v for v in cls.__dict__.values() if isinstance(v, Column)]
