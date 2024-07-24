from abc import abstractmethod
from collections.abc import Mapping
from dataclasses import asdict
from io import StringIO
from typing import Any, Dict

from flopy4.param import MFParam, MFParams, MFReader
from flopy4.scalar import MFScalar
from flopy4.utils import strip

PAD = "  "


class MFCompound(MFParam, MFParams):
    @abstractmethod
    def __init__(
        self,
        params,
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
        MFParams.__init__(self, {k: p.with_name(k) for k, p in params.items()})
        MFParam.__init__(
            self,
            block,
            name,
            type,
            longname,
            description,
            deprecated,
            in_record,
            layered,
            optional,
            numeric_index,
            preserve_case,
            repeating,
            tagged,
            reader,
            shape,
            default_value,
        )

    @property
    def params(self) -> MFParams:
        """Component parameters."""
        return self.data

    @property
    def value(self) -> Mapping[str, Any]:
        """Get component names/values."""
        return {
            k: s.value for k, s in self.data.items() if s.value is not None
        }

    @value.setter
    def value(self, **kwargs):
        """Set component names/values by keyword arguments."""
        val_len = len(kwargs)
        exp_len = len(self.data)
        if exp_len != val_len:
            raise ValueError(f"Expected {exp_len} values, got {val_len}")
        for key in self.data.keys():
            self.data[key].value = kwargs[key]


class MFRecord(MFCompound):
    def __init__(
        self,
        params,
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
            params,
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

    @classmethod
    def load(cls, f, params, **kwargs) -> "MFRecord":
        line = strip(f.readline()).lower()

        if not any(line):
            raise ValueError("Record line may not be empty")

        split = line.split()
        kwargs["name"] = split.pop(0).lower()
        line = " ".join(split)
        return cls(MFRecord.parse(line, params, **kwargs), **kwargs)

    @staticmethod
    def parse(line, params, **kwargs) -> Dict[str, MFScalar]:
        loaded = dict()

        for param_name, param in params.items():
            split = line.split()
            stype = type(param)
            words = len(param)
            head = " ".join(split[:words])
            tail = " ".join(split[words:])
            line = tail
            kwrgs = {**kwargs, **asdict(param)}
            with StringIO(head) as f:
                loaded[param_name] = stype.load(f, **kwrgs)

        return loaded

    def write(self, f):
        f.write(f"{PAD}{self.name.upper()}")
        last = len(self) - 1
        for i, param in enumerate(self.data.values()):
            param.write(f, newline=i == last)


class MFKeystring(MFCompound):
    def __init__(
        self,
        params,
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
            params,
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

    @classmethod
    def load(cls, f, params, **kwargs) -> "MFKeystring":
        """Load the keystring from file."""
        loaded = dict()

        while True:
            pos = f.tell()
            line = strip(f.readline()).lower()
            if line == "":
                raise ValueError("Early EOF")
            if line == "\n":
                continue

            split = line.split()
            key = split[0]

            if key == "end":
                f.seek(pos)
                break

            param = params.pop(key)
            kwrgs = {**kwargs, **asdict(param)}
            with StringIO(line) as ff:
                loaded[key] = type(param).load(ff, **kwrgs)

        return cls(loaded, **kwargs)

    def write(self, f):
        """Write the keystring to file."""
        for param in self.data:
            param.write(f)
