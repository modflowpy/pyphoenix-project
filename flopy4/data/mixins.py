import numpy as np


class MFArrayMixins:
    """
    Class containing standard python mathematical mixin functions for the
    MFArray Class.

    """
    def __init__(self):
        self._is_layered = None
        self._flat = None

    @property
    def raw_values(self):
        raise NotImplementedError(
            "raw_values must be implemented in child class"
        )

    @property
    def values(self):
        raise NotImplementedError(
            "values must be implemented in child class"
        )

    def __iadd__(self, other):
        if self._is_layered:
            for mfa in self._flat:
                mfa += other
            return self

        self._flat += other
        return self

    def __imul__(self, other):
        if self._is_layered:
            for mfa in self._flat:
                mfa *= other
            return self

        self._flat *= other
        return self

    def __isub__(self, other):
        if self._is_layered:
            for mfa in self._flat:
                mfa -= other
            return self

        self._flat -= other
        return self

    def __itruediv__(self, other):
        if self._is_layered:
            for mfa in self._flat:
                mfa /= other
            return self

        self._flat /= other
        return self

    def __ifloordiv__(self, other):
        if self._is_layered:
            for mfa in self._flat:
                mfa /= other
            return self

        self._flat /= other
        return self

    def __ipow__(self, other):
        if self._is_layered:
            for mfa in self._flat:
                mfa /= other
            return self

        self._flat **= other
        return self

    def __add__(self, other):
        if self._is_layered:
            for mfa in self._flat:
                mfa += other
            return self

        self._flat += other
        return self

    def __mul__(self, other):
        if self._is_layered:
            for mfa in self._flat:
                mfa *= other
            return self

        self._flat *= other
        return self

    def __sub__(self, other):
        if self._is_layered:
            for mfa in self._flat:
                mfa -= other
            return self

        self._flat -= other
        return self

    def __truediv__(self, other):
        if self._is_layered:
            for mfa in self._flat:
                mfa /= other
            return self

        self._flat /= other
        return self

    def __floordiv__(self, other):
        if self._is_layered:
            for mfa in self._flat:
                mfa /= other
            return self

        self._flat /= other
        return self

    def __pow__(self, other):
        if self._is_layered:
            for mfa in self._flat:
                mfa /= other
            return self

        self._flat **= other
        return self

    def __iter__(self):
        for i in self.raw_values.ravel():
            yield i

    def min(self):
        return np.nanmin(self.values)

    def mean(self):
        return np.nanmean(self.values)

    def median(self):
        return np.nanmedian(self.values)

    def max(self):
        return np.nanmax(self.values)

    def std(self):
        return np.nanstd(self.values)

    def sum(self):
        return np.nansum(self.values)