from enum import Enum


class How(Enum):
    internal = "INTERNAL"
    constant = "CONSTANT"
    external = "OPEN/CLOSE"
    binary = "OPEN/CLOSE"

    @classmethod
    def string(cls, how):
        return cls(how).value
