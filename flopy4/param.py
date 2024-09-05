from abc import abstractmethod
from ast import literal_eval
from collections import OrderedDict, UserDict
from dataclasses import dataclass, fields
from io import StringIO
from pprint import pformat
from typing import Any, Dict, Optional, Tuple

from flopy4.constants import MFReader


@dataclass
class MFParamSpec:
    """
    MF6 input parameter specification.
    """

    block: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    longname: Optional[str] = None
    description: Optional[str] = None
    deprecated: bool = False
    in_record: bool = False
    layered: bool = False
    optional: bool = True
    numeric_index: bool = False
    preserve_case: bool = False
    repeating: bool = False
    tagged: bool = True
    reader: MFReader = MFReader.urword
    shape: Optional[Tuple[int]] = None
    default_value: Optional[Any] = None

    @classmethod
    def fields(cls):
        """
        Get the MF6 input parameter field specification.
        These uniquely describe the MF6 input parameter.

        Notes
        -----
        This is equivalent to `dataclasses.fields(MFParamSpec)`.
        """
        return fields(cls)

    @classmethod
    def load(cls, f) -> "MFParamSpec":
        """
        Load an MF6 input input parameter specification
        from a definition file.
        """
        spec = dict()
        members = cls.fields()
        keywords = [f.name for f in members if f.type is bool]

        while True:
            line = f.readline()
            if not line or line == "\n":
                break
            words = line.strip().lower().split()
            key = words[0]
            val = " ".join(words[1:])
            if key in keywords:
                spec[key] = val == "true"
            elif key == "reader":
                spec[key] = MFReader.from_str(val)
            elif key == "shape":
                spec[key] = literal_eval(val)
            else:
                spec[key] = val

        return cls(**spec)

    def with_name(self, name) -> "MFParamSpec":
        """Set the parameter name and return the parameter."""
        self.name = name
        return self

    def with_block(self, block) -> "MFParamSpec":
        """Set the parameter block and return the parameter."""
        self.block = block
        return self


class MFParam(MFParamSpec):
    """
    MODFLOW 6 input parameter. Can be a scalar or compound of
    scalars, an array, or a list (i.e. a table).

    Notes
    -----
    This class plays a dual role: first, to define blocks that
    specify the input required for MF6 components; and second,
    as a data access layer by which higher components (blocks,
    packages, etc) can read/write parameters. The former is a
    developer task (though it may be automated as classes are
    generated from DFNs) while the latter happens at runtime,
    but both APIs are user-facing; the user can first inspect
    a package's specification via class attributes, then load
    an input file and inspect package data via instance attrs.

    Specification attributes are set at import time. A parent
    block or package defines parameters as class attributes,
    including a description, whether the parameter is optional,
    and other information specifying the parameter.

    The parameter's value is an instance attribute that is set
    at load time. The parameter's parent component introspects
    its constituent parameters then loads each parameter value
    from the input file. This is like "hydrating" a definition
    from a data store as in single-page web applications (e.g.
    React, Vue) or ORM frameworks (Django).
    """

    @abstractmethod
    def __init__(
        self,
        block=None,
        name=None,
        type=None,
        longname=None,
        description=None,
        deprecated=False,
        in_record=False,
        layered=False,
        optional=True,
        numeric_index=False,
        preserve_case=False,
        repeating=False,
        tagged=False,
        reader=MFReader.urword,
        shape=None,
        default_value=None,
    ):
        super().__init__(
            block=block,
            name=name,
            type=type,
            longname=longname,
            description=description,
            deprecated=deprecated,
            in_record=in_record,
            layered=layered,
            optional=optional,
            numeric_index=numeric_index,
            preserve_case=preserve_case,
            repeating=repeating,
            tagged=tagged,
            reader=reader,
            shape=shape,
            default_value=default_value,
        )

    def __str__(self):
        buffer = StringIO()
        self.write(buffer)
        return buffer.getvalue()

    def __eq__(self, other):
        if not isinstance(other, MFParam):
            raise TypeError(f"Expected MFParam, got {type(other)}")
        return self.value == other.value

    @property
    @abstractmethod
    def value(self) -> Optional[Any]:
        """Get the parameter's value, if loaded."""
        pass

    @abstractmethod
    def write(self, f, **kwargs):
        """Write the parameter to file."""
        pass


class MFParams(UserDict):
    """
    Mapping of parameter names to parameters. Acts like
    a dictionary, also supports named attribute access.
    """

    def __init__(self, params=None):
        MFParams.assert_params(params)
        super().__init__(params)
        for key, param in self.items():
            setattr(self, key, param)

    def __repr__(self):
        return pformat(self.data)

    def __eq__(self, other):
        if not isinstance(other, MFParams):
            raise TypeError(f"Expected MFParams, got {type(other)}")
        return OrderedDict(sorted(self.value)) == OrderedDict(
            sorted(other.value)
        )

    @staticmethod
    def assert_params(params):
        """
        Raise an error if any of the given items are not
        subclasses of `MFParam`.
        """
        if not params:
            return
        elif isinstance(params, dict):
            params = params.values()
        not_params = [
            p
            for p in params
            if p is not None and not issubclass(type(p), MFParam)
        ]
        if any(not_params):
            raise TypeError(f"Expected MFParam subclasses, got {not_params}")

    @property
    def value(self) -> Dict[str, Any]:
        """Get a dictionary of parameter values."""
        return {k: v.value for k, v in self.items()}

    @value.setter
    def value(self, value: Optional[Dict[str, Any]]):
        """Set parameter values from a dictionary."""

        if value is None or not any(value):
            return

        params = value.copy()
        MFParams.assert_params(params)
        self.update(params)
        for key, param in self.items():
            setattr(self, key, param)

    def write(self, f, **kwargs):
        """Write the parameters to file."""
        for param in self.values():
            if param.type == "record" or param.type == "recarray":
                if len(self.params[param.name]):
                    param.write(f, **kwargs)
            elif param.type is None:
                raise TypeError(
                    f"Unknown specification type for param '{param.name}'"
                )
            elif self.params[param.name] is not None:
                param.write(f, **kwargs)
