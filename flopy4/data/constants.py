from enum import Enum


class How(Enum):
    internal = "INTERNAL"
    constant = "CONSTANT"
    external = "OPEN/CLOSE"

    @classmethod
    def to_string(cls, how):
        return cls(how).value

    @classmethod
    def from_string(cls, string):
        for e in How:
            if string.upper() == e.value:
                return e


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