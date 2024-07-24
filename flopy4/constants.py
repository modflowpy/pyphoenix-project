from enum import Enum


class CommonNames:
    iprn = "IPRN"
    internal = "INTERNAL"
    constant = "CONSTANT"
    external = "OPEN/CLOSE"
    format = "FORMAT"
    structured = "structured"
    vertex = "vertex"
    unstructured = "unstructured"
    empty = ""
    end = "END"


class MFFileInout(Enum):
    filein = "filein"
    fileout = "fileout"

    @classmethod
    def from_str(cls, value):
        for e in cls:
            if value.lower() == e.value:
                return e


class MFReader(Enum):
    """
    MF6 procedure with which to read input.
    """

    urword = "urword"
    u1ddbl = "u1dbl"
    readarray = "readarray"

    @classmethod
    def from_str(cls, value):
        for e in cls:
            if value.lower() == e.value:
                return e
