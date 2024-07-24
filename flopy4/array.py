from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Optional

import numpy as np
import re
from flopy.utils.flopy_io import line_strip, multi_line_strip

from flopy4.constants import CommonNames
from flopy4.param import MFParam, MFReader


class NumPyArrayMixin:
    """
    Provides NumPy interoperability for `MFArray` implementations.
    This mixin makes an `MFArray` behave like a NumPy `ndarray`.

    Resources
    ---------
    - https://numpy.org/doc/stable/user/basics.interoperability.html
    - https://numpy.org/doc/stable/user/basics.ufuncs.html#ufuncs-basics

    """

    def __iadd__(self, other):
        if self.layered:
            for mfa in self._value:
                mfa += other
            return self

        self._value += other
        return self

    def __imul__(self, other):
        if self.layered:
            for mfa in self._value:
                mfa *= other
            return self

        self._value *= other
        return self

    def __isub__(self, other):
        if self.layered:
            for mfa in self._value:
                mfa -= other
            return self

        self._value -= other
        return self

    def __itruediv__(self, other):
        if self.layered:
            for mfa in self._value:
                mfa /= other
            return self

        self._value /= other
        return self

    def __ifloordiv__(self, other):
        if self.layered:
            for mfa in self._value:
                mfa /= other
            return self

        self._value /= other
        return self

    def __ipow__(self, other):
        if self.layered:
            for mfa in self._value:
                mfa /= other
            return self

        self._value **= other
        return self

    def __add__(self, other):
        if self.layered:
            for mfa in self._value:
                mfa += other
            return self

        self._value += other
        return self

    def __mul__(self, other):
        if self.layered:
            for mfa in self._value:
                mfa *= other
            return self

        self._value *= other
        return self

    def __sub__(self, other):
        if self.layered:
            for mfa in self._value:
                mfa -= other
            return self

        self._value -= other
        return self

    def __truediv__(self, other):
        if self.layered:
            for mfa in self._value:
                mfa /= other
            return self

        self._value /= other
        return self

    def __floordiv__(self, other):
        if self.layered:
            for mfa in self._value:
                mfa /= other
            return self

        self._value /= other
        return self

    def __pow__(self, other):
        if self.layered:
            for mfa in self._value:
                mfa /= other
            return self

        self._value **= other
        return self

    def __iter__(self):
        for i in self.raw.ravel():
            yield i

    def min(self):
        return np.nanmin(self.value)

    def mean(self):
        return np.nanmean(self.value)

    def median(self):
        return np.nanmedian(self.value)

    def max(self):
        return np.nanmax(self.value)

    def std(self):
        return np.nanstd(self.value)

    def sum(self):
        return np.nansum(self.value)


class MFArrayType(Enum):
    """
    How a MODFLOW 6 input array is represented in an input file.

    """

    internal = "INTERNAL"
    constant = "CONSTANT"
    external = "OPEN/CLOSE"

    @classmethod
    def to_string(cls, how):
        return cls(how).value

    @classmethod
    def from_string(cls, string):
        for e in MFArrayType:
            if string.upper() == e.value:
                return e


class MFArray(MFParam, NumPyArrayMixin):
    """
    A MODFLOW 6 array backed by a 1-dimensional NumPy array,
    which is reshaped as needed for various views. Supports
    array indexing as well as standard NumPy array ufuncs.
    """

    def __init__(
        self,
        shape,
        array=None,
        how=MFArrayType.internal,
        factor=None,
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
        default_value=None,
    ):
        MFParam.__init__(
            self,
            shape=shape,
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
            default_value=default_value,
        )
        self._value = array
        self._shape = shape
        self._how = how
        self._factor = factor

    def __getitem__(self, item):
        return self.raw[item]

    def __setitem__(self, key, value):
        values = self.raw
        values[key] = value
        if self.layered:
            for ix, mfa in enumerate(self._value):
                mfa[:] = values[ix]
            return

        values = values.ravel()
        if self._how == MFArrayType.constant:
            if not np.allclose(values, values[0]):
                self._how = MFArrayType.internal
                self._value = values
            else:
                self._value = values[0]
        else:
            self._value = values

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        raw = self.raw
        if len(inputs) == 1:
            result = raw.__array_ufunc__(ufunc, method, raw, **kwargs)
        else:
            result = raw.__array_ufunc__(
                ufunc, method, raw, *inputs[1:], kwargs
            )
        if not isinstance(result, np.ndarray):
            raise NotImplementedError(f"{str(ufunc)} has not been implemented")

        if result.shape != self._shape:
            raise AssertionError(
                f"{str(ufunc)} is not supported for inplace operations on "
                f"MFArray objects"
            )

        tmp = [None for _ in self._shape]
        self.__setitem__(slice(*tmp), result)
        return self

    @property
    def value(self) -> np.ndarray:
        """
        Return the array.
        """
        if self.layered:
            arr = []
            for mfa in self._value:
                arr.append(mfa.value)
            return np.array(arr)

        if self._how == MFArrayType.constant:
            return np.ones(self._shape) * self._value * self.factor
        else:
            return self._value.reshape(self._shape) * self.factor

    @property
    def raw(self):
        """
        Return the array without multiplying by `self.factor`.
        """
        if self.layered:
            arr = []
            for mfa in self._value:
                arr.append(mfa.raw)
            return np.array(arr)

        if self._how == MFArrayType.constant:
            return np.ones(self._shape) * self._value
        else:
            return self._value.reshape(self._shape)

    @property
    def factor(self) -> Optional[float]:
        """
        Optional factor by which to multiply array elements.
        """
        if self.layered:
            factor = [mfa.factor for mfa in self._value]
            return factor

        factor = self._factor
        if self._factor is None:
            factor = 1.0
        return factor

    @property
    def how(self):
        """
        How the array is to be written to the input file.
        """
        if self.layered:
            how = [mfa.how for mfa in self._value]
            return how

        return self._how

    def write(self, f):
        # todo
        pass

    @classmethod
    def load(cls, f, cwd, shape, header=True, **kwargs):
        layered = kwargs.pop("layered", False)

        if header:
            tokens = multi_line_strip(f).split()
            name = tokens[0]
            kwargs.pop("name", None)
            if len(tokens) > 1 and tokens[1] == "layered":
                layered = True
        else:
            name = kwargs.pop("name", None)

        if layered:
            nlay = shape[0]
            lshp = shape[1:]
            objs = []
            for _ in range(nlay):
                mfa = cls._load(f, cwd, lshp, name)
                objs.append(mfa)

            return MFArray(
                shape,
                array=np.array(objs, dtype=object),
                how=None,
                factor=None,
                name=name,
                layered=True,
            )
        else:
            kwargs.pop("layered", None)
            return cls._load(
                f, cwd, shape, layered=layered, name=name, **kwargs
            )

    @classmethod
    def _load(cls, f, cwd, shape, layered=False, **kwargs):
        control_line = multi_line_strip(f).split()

        if CommonNames.iprn.lower() in control_line:
            idx = control_line.index(CommonNames.iprn.lower())
            control_line.pop(idx + 1)
            control_line.pop(idx)

        how = MFArrayType.from_string(control_line[0])
        clpos = 1

        if how == MFArrayType.internal:
            array = cls.read_array(f)

        elif how == MFArrayType.constant:
            array = float(control_line[clpos])
            clpos += 1

        elif how == MFArrayType.external:
            ext_path = Path(control_line[clpos])
            fpath = cwd / ext_path
            with open(fpath) as foo:
                array = cls.read_array(foo)
            clpos += 1

        else:
            raise NotImplementedError()

        factor = None
        if len(control_line) > 2:
            factor = float(control_line[clpos + 1])

        return cls(shape, array=array, how=how, factor=factor, **kwargs)

    @staticmethod
    def read_array(f):
        """
        Read a MODFLOW 6 array from an open file
        into a flat NumPy array representation.
        """

        astr = []
        while True:
            pos = f.tell()
            line = f.readline()
            line = line_strip(line)
            if not re.match("^[0-9. ]+$", line):
                f.seek(pos, 0)
                break
            astr.append(line)

        astr = StringIO(" ".join(astr))
        array = np.genfromtxt(astr).ravel()
        return array
