from abc import abstractmethod
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from flopy4.parameter import MFParameter, MFParamSpec
from flopy4.utils import strip


def _asdict(spec: Optional[MFParamSpec]):
    return dict() if spec is None else asdict(spec)


class MFScalar(MFParameter):
    @abstractmethod
    def __init__(
        self, name=None, longname=None, description=None, optional=False
    ):
        super().__init__(name, longname, description, optional)


class MFKeyword(MFScalar):
    def __init__(
        self, name=None, longname=None, description=None, optional=False
    ):
        super().__init__(name, longname, description, optional)
        self._value = False

    @property
    def value(self):
        return self._value

    @classmethod
    def load(cls, f, spec: Optional[MFParamSpec] = None) -> "MFKeyword":
        line = strip(f.readline()).lower()

        if not any(line):
            raise ValueError("Keyword line may not be empty")
        if " " in line:
            raise ValueError("Keyword may not contain spaces")

        scalar = cls(name=line, **_asdict(spec))
        scalar._value = True
        return scalar

    def write(self, f):
        if self.value:
            f.write(f"{self.name.upper()}\n")


class MFInteger(MFScalar):
    def __init__(
        self, name=None, longname=None, description=None, optional=False
    ):
        super().__init__(name, longname, description, optional)
        self._value = 0

    @property
    def value(self):
        return self._value

    @classmethod
    def load(cls, f, spec: Optional[MFParamSpec] = None) -> "MFInteger":
        line = strip(f.readline()).lower()
        words = line.split()

        if len(words) != 2:
            raise ValueError("Expected space-separated: 1) keyword, 2) value")

        scalar = cls(name=words[0], **_asdict(spec))
        scalar._value = int(words[1])
        return scalar

    def write(self, f):
        f.write(f"{self.name.upper()} {self.value}\n")


class MFDouble(MFScalar):
    def __init__(
        self, name=None, longname=None, description=None, optional=False
    ):
        super().__init__(name, longname, description, optional)
        self._value = 0.0

    @property
    def value(self):
        return self._value

    @classmethod
    def load(cls, f, spec: Optional[MFParamSpec] = None) -> "MFDouble":
        line = strip(f.readline()).lower()
        words = line.split()

        if len(words) != 2:
            raise ValueError("Expected space-separated: 1) keyword, 2) value")

        scalar = cls(name=words[0], **_asdict(spec))
        scalar._value = float(words[1])
        return scalar

    def write(self, f):
        f.write(f"{self.name.upper()} {self.value}\n")


class MFString(MFScalar):
    def __init__(
        self, name=None, longname=None, description=None, optional=False
    ):
        super().__init__(name, longname, description, optional)
        self._value = None

    @property
    def value(self):
        return self._value

    @classmethod
    def load(cls, f, spec: Optional[MFParamSpec] = None) -> "MFString":
        line = strip(f.readline()).lower()
        words = line.split()

        if len(words) != 2:
            raise ValueError("Expected space-separated: 1) keyword, 2) value")

        scalar = cls(name=words[0], **_asdict(spec))
        scalar._value = words[1]
        return scalar

    def write(self, f):
        f.write(f"{self.name.upper()} {self.value}\n")


class MFFilename(MFScalar):
    def __init__(
        self, name=None, longname=None, description=None, optional=False
    ):
        super().__init__(name, longname, description, optional)
        self._value = None

    @property
    def value(self):
        return self._value

    @classmethod
    def load(cls, f, spec: Optional[MFParamSpec] = None) -> "MFFilename":
        line = strip(f.readline())
        words = line.split()

        if len(words) != 3 or words[1].lower() not in ["filein", "fileout"]:
            raise ValueError(
                "Expected space-separated: "
                "1) keyword, "
                "2) FILEIN or FILEOUT, "
                "3) file path"
            )

        scalar = cls(name=words[0].lower(), **_asdict(spec))
        scalar._value = Path(words[2])
        return scalar

    def write(self, f):
        f.write(f"{self.name.upper()} {self.value}\n")
