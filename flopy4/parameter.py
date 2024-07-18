from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class MFReader(Enum):
    """
    MF6 procedure with which to read input.
    """

    urword = "URWORD"
    u1ddbl = "U1DDBL"
    readarray = "READARRAY"

    @classmethod
    def from_string(cls, string):
        for e in cls:
            if string.upper() == e.value:
                return e


@dataclass
class MFParamSpec:
    """
    MF6 input parameter specification.
    """

    block: Optional[str] = None
    name: Optional[str] = None
    longname: Optional[str] = None
    description: Optional[str] = None
    deprecated: bool = False
    in_record: bool = False
    layered: bool = False
    optional: bool = True
    numeric_index: bool = False
    repeating: bool = False
    tagged: bool = True
    reader: MFReader = MFReader.urword
    default_value: Optional[Any] = None

    @classmethod
    def load(cls, f) -> "MFParamSpec":
        spec = dict()
        while True:
            line = f.readline()
            if not line or line == "\n":
                break
            words = line.strip().lower().split()
            key = words[0]
            val = " ".join(words[1:])
            # todo dynamically load properties and
            # filter by type instead of hardcoding
            if key in [
                "block",
                "name",
                "longname",
                "description",
                "reader",
            ]:
                spec[key] = val
            elif key in [
                "deprecated",
                "in_record",
                "layered",
                "optional",
                "numeric_index",
                "repeating",
                "tagged",
            ]:
                spec[key] = val == "true"
            elif key == "reader":
                spec[key] = MFReader.from_string(val)
        return cls(**spec)


class MFParameter(ABC):
    """
    MODFLOW 6 input parameter. Can be a scalar or compound of
    scalars, an array, or a list (i.e. a table). `MFParameter`
    classes play a dual role: first, to define the blocks that
    specify the input required for MF6 components; and second,
    as a data access layer by which higher components (blocks,
    packages, etc) can read/write parameters. The former is a
    developer task (though it may be automated as classes are
    generated from DFNs) while the latter are user-facing APIs.

    Notes
    -----
    Specification attributes are set at import time. A parent
    block, when defining parameters as class attributes, will
    supply a description, whether the parameter is mandatory,
    and other information comprising the input specification.

    The parameter's value is an instance attribute that is set
    at load time. The parameter's parent block will introspect
    its constituent parameters, then load each parameter value
    from the input file and assign an eponymous attribute with
    a value property. This is akin to "hydrating" a definition
    from a data store as in single-page web applications (e.g.
    React, Vue) or ORM frameworks (Django).
    """

    @abstractmethod
    def __init__(
        self,
        name=None,
        longname=None,
        description=None,
        deprecated=False,
        in_record=False,
        layered=False,
        optional=True,
        numeric_index=False,
        repeating=False,
        tagged=False,
        reader=MFReader.urword,
        default_value=None,
    ):
        self.spec = MFParamSpec(
            name=name,
            longname=None,
            description=description,
            deprecated=deprecated,
            in_record=in_record,
            layered=layered,
            optional=optional,
            numeric_index=numeric_index,
            repeating=repeating,
            tagged=tagged,
            reader=reader,
            default_value=default_value,
        )

    @property
    def name(self):
        """Get the parameter's name."""
        return self.spec.name

    @property
    @abstractmethod
    def value(self):
        """Get the parameter's value."""
        pass
