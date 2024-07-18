from abc import abstractmethod
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Optional

from flopy4.parameter import MFParameter, MFParamSpec, MFReader
from flopy4.utils import strip

PAD = "  "


def _as_dict(spec: Optional[MFParamSpec]) -> dict:
    return dict() if spec is None else asdict(spec)


def _or_empty(spec: Optional[MFParamSpec]) -> MFParamSpec:
    return MFParamSpec() if spec is None else spec


class MFScalar(MFParameter):
    @abstractmethod
    def __init__(
        self,
        value=None,
        block=None,
        name=None,
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
        default_value=None,
    ):
        self._value = value
        super().__init__(
            block,
            name,
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
            default_value,
        )

    @property
    def value(self):
        return self._value


class MFKeyword(MFScalar):
    def __init__(
        self,
        value=None,
        block=None,
        name=None,
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
        default_value=None,
    ):
        super().__init__(
            value,
            block,
            name,
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
            default_value,
        )

    @classmethod
    def load(cls, f, spec: Optional[MFParamSpec] = None) -> "MFKeyword":
        line = strip(f.readline()).lower()

        if not any(line):
            raise ValueError("Keyword line may not be empty")
        if " " in line:
            raise ValueError("Keyword may not contain spaces")

        spec = _or_empty(spec)
        spec.name = line
        return cls(value=True, **_as_dict(spec))

    def write(self, f):
        if self.value:
            f.write(f"{PAD}{self.name.upper()}\n")


class MFInteger(MFScalar):
    def __init__(
        self,
        value=None,
        block=None,
        name=None,
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
        default_value=None,
    ):
        super().__init__(
            value,
            block,
            name,
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
            default_value,
        )

    @classmethod
    def load(cls, f, spec: Optional[MFParamSpec] = None) -> "MFInteger":
        line = strip(f.readline()).lower()
        words = line.split()

        if len(words) != 2:
            raise ValueError("Expected space-separated: 1) keyword, 2) value")

        spec = _or_empty(spec)
        spec.name = words[0]
        return cls(value=int(words[1]), **_as_dict(spec))

    def write(self, f):
        f.write(f"{PAD}{self.name.upper()} {self.value}\n")


class MFDouble(MFScalar):
    def __init__(
        self,
        value=None,
        block=None,
        name=None,
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
        default_value=None,
    ):
        super().__init__(
            value,
            block,
            name,
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
            default_value,
        )

    @classmethod
    def load(cls, f, spec: Optional[MFParamSpec] = None) -> "MFDouble":
        line = strip(f.readline()).lower()
        words = line.split()

        if len(words) != 2:
            raise ValueError("Expected space-separated: 1) keyword, 2) value")

        spec = _or_empty(spec)
        spec.name = words[0]
        return cls(value=float(words[1]), **_as_dict(spec))

    def write(self, f):
        f.write(f"{PAD}{self.name.upper()} {self.value}\n")


class MFString(MFScalar):
    def __init__(
        self,
        value=None,
        block=None,
        name=None,
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
        default_value=None,
    ):
        super().__init__(
            value,
            block,
            name,
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
            default_value,
        )

    @classmethod
    def load(cls, f, spec: Optional[MFParamSpec] = None) -> "MFString":
        line = strip(f.readline()).lower()
        words = line.split()

        if len(words) != 2:
            raise ValueError("Expected space-separated: 1) keyword, 2) value")

        spec = _or_empty(spec)
        spec.name = words[0]
        return cls(value=words[1], **_as_dict(spec))

    def write(self, f):
        f.write(f"{PAD}{self.name.upper()} {self.value}\n")


class MFFileInout(Enum):
    filein = "filein"
    fileout = "fileout"

    @classmethod
    def from_str(cls, value):
        for e in cls:
            if value.lower() == e.value:
                return e


class MFFilename(MFScalar):
    def __init__(
        self,
        inout=MFFileInout.filein,
        value=None,
        block=None,
        name=None,
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
        default_value=None,
    ):
        self.inout = inout
        super().__init__(
            value,
            block,
            name,
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
            default_value,
        )

    @classmethod
    def load(cls, f, spec: Optional[MFParamSpec] = None) -> "MFFilename":
        line = strip(f.readline())
        words = line.split()
        inout = [io.name for io in MFFileInout]

        if len(words) != 3 or words[1].lower() not in inout:
            raise ValueError(
                "Expected space-separated: "
                "1) keyword, "
                f"2) {' or '.join(MFFileInout.from_str(words[1]))}"
                "3) file path"
            )

        spec = _or_empty(spec)
        spec.name = words[0].lower()
        return cls(
            inout=MFFileInout.from_str(words[1]),
            value=Path(words[2]),
            **_as_dict(spec),
        )

    def write(self, f):
        f.write(
            f"{PAD}{self.name.upper()} "
            f"{self.inout.value.upper()} "
            f"{self.value}\n"
        )
