from abc import ABC

from xattree import xattree

from flopy4.mf6.component import Component


@xattree
class Model(Component, ABC):
    pass
