from typing import ClassVar

from xattree import xattree

from flopy4.mf6.solution import Solution


@xattree
class Ems(Solution):
    slntype: ClassVar[str] = "ems"
