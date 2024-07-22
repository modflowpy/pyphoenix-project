from abc import abstractmethod
from collections import UserList
from io import StringIO
from typing import Any, Iterator, List, Tuple

from flopy4.parameter import MFParameter, MFReader
from flopy4.scalar import MFScalar
from flopy4.utils import strip

PAD = "  "


class MFCompound(MFParameter, UserList):
    @abstractmethod
    def __init__(
        self,
        scalars,
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
        MFParameter.__init__(
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
        UserList.__init__(self, scalars)


class MFRecord(MFCompound):
    def __init__(
        self,
        scalars,
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
            scalars,
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

    @property
    def scalars(self) -> Tuple[MFScalar]:
        return tuple(self.data.copy())

    @property
    def value(self) -> Tuple[Any]:
        return tuple([s.value for s in self.data])

    @value.setter
    def value(self, value: Tuple[Any]):
        assert len(value) == len(self.data)
        for i in range(len(self.data)):
            self.data[i].value = value[i]

    @classmethod
    def load(cls, f, scalars, **kwargs) -> "MFRecord":
        line = strip(f.readline()).lower()

        if not any(line):
            raise ValueError("Record line may not be empty")

        split = line.split()
        kwargs["name"] = split.pop(0).lower()
        line = " ".join(split)
        return cls(list(MFRecord.parse(line, scalars, **kwargs)), **kwargs)

    @staticmethod
    def parse(line, scalars, **kwargs) -> Iterator[MFScalar]:
        for scalar in scalars:
            split = line.split()
            stype = type(scalar)
            words = len(scalar)
            head = " ".join(split[:words])
            tail = " ".join(split[words:])
            line = tail
            with StringIO(head) as f:
                yield stype.load(f, **kwargs)

    def write(self, f):
        f.write(f"{PAD}{self.name.upper()}")
        last = len(self) - 1
        for i, param in enumerate(self.data):
            param.write(f, newline=i == last)


class MFKeystring(MFCompound):
    def __init__(
        self,
        scalars,
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
            scalars,
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

    @property
    def scalars(self) -> List[MFScalar]:
        return self.data.copy()

    @property
    def value(self) -> List[Any]:
        return [s.value for s in self.data]

    @value.setter
    def value(self, value: List[Any]):
        assert len(value) == len(self.data)
        for i in range(len(self.data)):
            self.data[i].value = value[i]

    @classmethod
    def load(cls, f, scalars, **kwargs) -> "MFKeystring":
        loaded = []

        while True:
            line = strip(f.readline()).lower()
            if line == "":
                raise ValueError("Early EOF, aborting")
            if line == "\n":
                break

            scalar = scalars.pop()
            loaded.append(type(scalar).load(line, **kwargs))

        return cls(loaded, **kwargs)

    def write(self, f):
        for param in self.data:
            param.write(f)
