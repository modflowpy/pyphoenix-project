from abc import abstractmethod
from pathlib import Path
from typing import Generic, Optional, TypeVar, get_args

from flopy4.constants import MFFileInout
from flopy4.param import MFParam, MFReader
from flopy4.utils import strip

PAD = "  "
T = TypeVar("T")


class MFScalar(MFParam, Generic[T]):
    @abstractmethod
    def __init__(
        self,
        value=None,
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
        self._value = value
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

    def __init_subclass__(cls):
        cls.T = get_args(cls.__orig_bases__[0])[0]
        super().__init_subclass__()

    @property
    def value(self) -> T:
        return self._value

    @value.setter
    def value(self, value: Optional[T]):
        if value is None:
            return

        t = type(value)
        if issubclass(t, MFScalar):
            self._value = value.value
        elif t is type(self).T:
            self._value = value
        else:
            raise ValueError(f"Unsupported scalar: {value}")


class MFKeyword(MFScalar[bool]):
    def __init__(
        self,
        value=None,
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
            value,
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

    def __len__(self):
        return 1

    @classmethod
    def load(cls, f, **kwargs) -> "MFKeyword":
        line = strip(f.readline()).lower()

        if not any(line):
            raise ValueError("Keyword line may not be empty")
        if " " in line:
            raise ValueError("Keyword may not contain spaces")

        kwargs["name"] = line
        return cls(value=True, **kwargs)

    def write(self, f, **kwargs):
        newline = kwargs.pop("newline", True)
        if self.value:
            f.write(
                f"{PAD}" f"{self.name.upper()}" + ("\n" if newline else "")
            )


class MFInteger(MFScalar[int]):
    def __init__(
        self,
        value=None,
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
            value,
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

    def __len__(self):
        return 2

    @property
    def vtype(self):
        return int

    @classmethod
    def load(cls, f, **kwargs) -> "MFInteger":
        line = strip(f.readline()).lower()
        words = line.split()

        if len(words) != 2:
            raise ValueError("Expected space-separated: 1) keyword, 2) value")

        kwargs["name"] = words[0]
        return cls(value=int(words[1]), **kwargs)

    def write(self, f, **kwargs):
        newline = kwargs.pop("newline", True)
        f.write(
            f"{PAD}"
            f"{self.name.upper()} "
            f"{self.value}" + ("\n" if newline else "")
        )


class MFDouble(MFScalar[float]):
    def __init__(
        self,
        value=None,
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
            value,
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

    def __len__(self):
        return 2

    @classmethod
    def load(cls, f, **kwargs) -> "MFDouble":
        line = strip(f.readline()).lower()
        words = line.split()

        if len(words) != 2:
            raise ValueError("Expected space-separated: 1) keyword, 2) value")

        kwargs["name"] = words[0]
        return cls(value=float(words[1]), **kwargs)

    def write(self, f, **kwargs):
        newline = kwargs.pop("newline", True)
        f.write(
            f"{PAD}"
            f"{self.name.upper()} "
            f"{self.value}" + ("\n" if newline else "")
        )


class MFString(MFScalar[str]):
    def __init__(
        self,
        value=None,
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
            value,
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

    def __len__(self):
        return 0 if self._value is None else len(self._value.split())

    @classmethod
    def load(cls, f, **kwargs) -> "MFString":
        line = strip(f.readline()).lower()
        words = line.split()

        if len(words) != 2:
            raise ValueError("Expected space-separated: 1) keyword, 2) value")

        kwargs["name"] = words[0]
        return cls(value=words[1], **kwargs)

    def write(self, f, **kwargs):
        newline = kwargs.pop("newline", True)
        f.write(
            f"{PAD}"
            f"{self.name.upper()} "
            f"{self.value}" + ("\n" if newline else "")
        )


class MFFilename(MFScalar[Path]):
    def __init__(
        self,
        inout=MFFileInout.filein,
        value=None,
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
        self.inout = inout
        super().__init__(
            value,
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

    def __len__(self):
        return 3

    @classmethod
    def load(cls, f, **kwargs) -> "MFFilename":
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

        kwargs["name"] = words[0].lower()
        return cls(
            inout=MFFileInout.from_str(words[1]),
            value=Path(words[2]),
            **kwargs,
        )

    def write(self, f, **kwargs):
        newline = kwargs.pop("newline", True)
        f.write(
            f"{PAD}{self.name.upper()} "
            f"{self.inout.value.upper()} "
            f"{self.value}" + ("\n" if newline else "")
        )
