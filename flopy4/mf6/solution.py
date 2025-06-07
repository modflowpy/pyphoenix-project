from abc import ABC

from xattree import xattree

from flopy4.mf6.package import Package


@xattree
class Solution(Package, ABC):
    """Base class for MF6 solution packages."""

    pass
