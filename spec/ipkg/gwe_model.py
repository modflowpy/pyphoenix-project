# generated file
from flopy4.model import MFModel
from flopy4.resolver import Resolve
from spec.ipkg.gwe_dis import GweDis


class GweModel(MFModel, Resolve):
    dis6 = GweDis()
