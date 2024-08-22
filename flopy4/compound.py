from abc import abstractmethod
from dataclasses import asdict
from io import StringIO
from typing import Any, Dict, Optional

import numpy as np

from flopy4.array import MFArray, MFArrayType
from flopy4.param import MFParam, MFParams, MFReader
from flopy4.scalar import MFDouble, MFInteger, MFScalar
from flopy4.utils import strip

PAD = "  "


def get_compound(
    params: Dict[str, MFParam], scalar: str = None
) -> Dict[str, "MFCompound"]:
    """
    Find compound parameters in the given parameter collection,
    optionally filtering by a scalar parameter name.
    """
    compounds = dict()
    for name, param in params.items():
        if isinstance(param, (MFRecord, MFKeystring, MFList)):
            if scalar is None or scalar in param:
                compounds[name] = param
    return compounds


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
        return MFParams(self.data)

    @property
    def value(self) -> Dict[str, Any]:
        """Get component names/values."""
        return {
            k: s.value for k, s in self.data.items() if s.value is not None
        }

    @value.setter
    def value(self, value: Optional[Dict[str, Any]]):
        """Set component names/values."""

        if value is None:
            return

        for key, val in value.items():
            self.data[key].value = val


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
            params=params,
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
        """Load a record with the given component parameters from a file."""
        line = strip(f.readline()).lower()

        if not any(line):
            raise ValueError("Record line may not be empty")

        split = line.split()
        kwargs["name"] = split.pop(0).lower()
        line = " ".join(split)
        return cls(MFRecord.parse(line, params, **kwargs), **kwargs)

    @staticmethod
    def parse(line, params, **kwargs) -> Dict[str, MFScalar]:
        """Parse a record with the given component parameters from a string."""

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

    def write(self, f, **kwargs):
        """Write the record to file."""
        f.write(f"{PAD}{self.name.upper()}")
        last = len(self) - 1
        for i, param in enumerate(self.data.values()):
            param.write(f, newline=i == last, **kwargs)


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
            params=params,
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

    def write(self, f, **kwargs):
        """Write the keystring to file."""
        super().write(f, **kwargs)


class MFScalarList(MFScalar[type]):
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
        return len(self._value)


class MFList(MFCompound):
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
            params=params,
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
    def load(cls, f, **kwargs) -> "MFList":
        """Load list input with the given component parameters from a file."""

        blk_params = kwargs.pop("blk_params", {})
        params = kwargs.pop("params", None)
        kwargs.pop("type", None)
        kwargs.pop("shape", None)

        param_lists = []
        # TODO: support multi-dimensional params
        for i in range(len(params)):
            param_lists.append(list())

        while True:
            pos = f.tell()
            line = f.readline()
            if line.lower().startswith("end"):
                f.seek(pos)
                break
            else:
                tokens = line.split()
                assert len(tokens) == len(param_lists)
                for i, token in enumerate(tokens):
                    param_lists[i].append(token)

        if blk_params and "dimensions" in blk_params:
            nbound = blk_params.get("dimensions").get("nbound")
            if nbound:
                for param_list in param_lists:
                    if len(param_list) > nbound:
                        raise ValueError("MFList nbound not satisfied")

        list_params = MFList.create_list_params(params, param_lists, **kwargs)
        return cls(list_params, **kwargs)

    @staticmethod
    def create_list_params(
        params: Dict[str, MFParam],
        param_lists: list,
        **kwargs,
    ) -> Dict[str, MFParam]:
        """Load model name file packages"""
        idx = 0
        list_params = dict()
        for param_name, param in params.items():
            if type(param) is MFDouble:
                list_params[param_name] = MFArray(
                    shape=len(param_lists[idx]),
                    array=np.array(param_lists[idx], dtype=np.float64),
                    how=MFArrayType.internal,
                    factor=1.0,
                    path=None,
                    **kwargs,
                )
            elif type(param) is MFInteger:
                list_params[param_name] = MFArray(
                    shape=len(param_lists[idx]),
                    array=np.array(param_lists[idx], dtype=np.int32),
                    how=MFArrayType.internal,
                    factor=1,
                    path=None,
                    **kwargs,
                )
            else:
                list_params[param_name] = MFScalarList(
                    value=param_lists[idx],
                    # type=MFScalarList,
                    type=type(param),
                    **kwargs,
                )

            idx += 1
        return list_params

    def write(self, f, **kwargs):
        """Write the list to file."""
        pass
