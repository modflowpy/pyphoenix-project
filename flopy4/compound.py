from abc import abstractmethod
from collections import UserList
from typing import Any, List, Tuple

from flopy4.parameter import MFParameter, MFReader
from flopy4.scalar import MFScalar
from flopy4.utils import strip


class MFCompound(MFParameter, UserList):
    @abstractmethod
    def __init__(
        self,
        *components,
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
        shape=None,
        default_value=None,
    ):
        UserList.__init__(self, list(components))


class MFRecord(MFCompound):
    def __init__(
        self,
        *components,
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
            *components,
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
    def value(self) -> Tuple[Any]:
        return tuple([s.value for s in self.data])

    @value.setter
    def value(self, value: Tuple[Any]):
        assert len(value) == len(self.data)
        for i in range(len(self.data)):
            self.data[i].value = value[i]

    @classmethod
    def load(cls, f, *components, **kwargs) -> "MFRecord":
        line = strip(f.readline()).lower()

        if not any(line):
            raise ValueError("Record line may not be empty")

        kwargs["name"] = line.split()[0].lower()
        scalars = MFRecord.parse(line, *components)
        return cls(*scalars, **kwargs)

    @staticmethod
    def parse(line, *components) -> List[MFScalar]:
        # todo
        pass


class MFKeystring(MFCompound):
    def __init__(
        self,
        *components,
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
            *components,
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
    def value(self) -> List[Any]:
        return [s.value for s in self.data]

    @value.setter
    def value(self, value: List[Any]):
        assert len(value) == len(self.data)
        for i in range(len(self.data)):
            self.data[i].value = value[i]

    @classmethod
    def load(cls, f, *components, **kwargs) -> "MFKeystring":
        scalars = []

        while True:
            line = strip(f.readline()).lower()
            if line == "":
                raise ValueError("Early EOF, aborting")
            if line == "\n":
                break

            scalars.append(MFKeystring.parse(line, *components))

        return cls(*scalars, **kwargs)

    @staticmethod
    def parse(line, *components) -> List[MFScalar]:
        # todo
        pass
