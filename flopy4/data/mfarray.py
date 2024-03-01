import numpy as np
from pathlib import Path
from io import StringIO
from .constants import How
from .mixins import MFArrayMixins
from flopy.datbase import DataType, DataInterface
from flopy.utils.flopy_io import multi_line_strip, line_strip


class MFArray(DataInterface, MFArrayMixins):
    """

    """
    def __init__(self, array, shape, how, factor=None, layered=False):
        super().__init__()
        self._flat = array
        self._shape = shape
        self._how = how
        self._factor = factor
        self._is_layered = layered

    @property
    def values(self):
        """

        Returns
        -------

        """
        if self._is_layered:
            arr = []
            for mfa in self._flat:
                arr.append(mfa.values)
            return np.array(arr)

        if self._how == How.constant:
            return np.ones(self._shape) * self._flat * self.factor
        else:
            return self._flat.reshape(self._shape) * self.factor

    @property
    def raw_values(self):
        """

        Returns
        -------

        """
        if self._is_layered:
            arr = []
            for mfa in self._flat:
                arr.append(mfa.raw_values)
            return np.array(arr)

        if self._how == How.constant:
            return np.ones(self._shape) * self._flat
        else:
            return self._flat.reshape(self._shape)

    @property
    def factor(self):
        """

        Returns
        -------

        """
        if self._is_layered:
            factor = [mfa.factor for mfa in self._flat]
            return factor

        factor = self._factor
        if self._factor is None:
            factor = 1.
        return factor

    @property
    def how(self):
        """

        Returns
        -------

        """
        if self._is_layered:
            how = [mfa.how for mfa in self._flat]
            return how

        return self._how

    def __getitem__(self, item):
        """

        Parameters
        ----------
        item

        Returns
        -------

        """
        return self.raw_values[item]

    def __setitem__(self, key, value):
        """

        Parameters
        ----------
        key
        value

        Returns
        -------

        """
        values = self.raw_values
        values[key] = value
        if self._is_layered:
            for ix, mfa in enumerate(self._flat):
                mfa[:] = values[ix]
            return

        values = values.ravel()
        if self._how == How.constant:
            if not np.allclose(values, values[0]):
                self._how = How.internal
                self._flat = values
            else:
                self._flat = values[0]
        else:
            self._flat = values

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        raw = self.raw_values
        result = raw.__array_ufunc__(ufunc, method, raw, **kwargs)
        if not isinstance(result, np.ndarray):
            raise NotImplementedError(f"{str(ufunc)} has not been implemented")

        tmp = [None for _ in self._shape]
        self.__setitem__(slice(*tmp), result)
        return self

    def _check_if_compatible(self):
        return

    @classmethod
    def load(cls, f, cwd, shape, layered=False):
        """

        Parameters
        ----------
        f

        Returns
        -------
            MFArray
        """
        if layered:
            nlay = shape[0]
            lay_shape = shape[1:]
            objs = []
            for lay in range(nlay):
                mfa = cls._loader(f, cwd, lay_shape)
                objs.append(mfa)

            mfa = MFArray(
                np.array(objs, dtype=object),
                shape,
                how=None,
                factor=None,
                layered=True
            )

        else:
            mfa = cls._loader(f, cwd, shape, layered=layered)

        return mfa

    @classmethod
    def _loader(cls, f, cwd, shape, layered=False):
        """

        Parameters
        ----------
        f
        cwd
        shape
        layered

        Returns
        -------

        """
        control_line = multi_line_strip(f).split()
        how = How.from_string(control_line[0])
        clpos = 1

        if how == How.internal:
            array = f_to_array(f)

        elif how == How.constant:
            array = float(control_line[clpos])
            clpos += 1

        elif how == how.external:
            ext_path = Path(control_line[clpos])
            fpath = cwd / ext_path
            with open(fpath) as foo:
                array = f_to_array(foo)
            clpos += 1

        else:
            raise NotImplementedError()

        factor = None
        if len(control_line) > 2:
            factor = float(control_line[clpos + 1])

        mfa = MFArray(array, shape, how, factor=factor)
        return mfa


def f_to_array(f):
    astr = []
    while True:
        pos = f.tell()
        line = f.readline()
        line = line_strip(line)
        if line in ("", "INTERNAL", "OPEN/CLOSE"):
            f.seek(pos, 0)
            break
        astr.append(line)

    astr = StringIO(" ".join(astr))
    array = np.genfromtxt(astr).ravel()
    return array

