# generated file
from flopy4.model import MFModel
from flopy4.resolver import Resolve
from flopy4.ispec.gwe_dis import GweDis
from flopy4.ispec.gwe_disu import GweDisu
from flopy4.ispec.gwe_disv import GweDisv


class GweModel(MFModel, Resolve):
    dis6 = GweDis()
    disu6 = GweDisu()
    disv6 = GweDisv()
