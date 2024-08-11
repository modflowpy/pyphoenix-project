# generated file
from flopy4.model import MFModel
from flopy4.resolver import Resolve
from spec.ipkg.prt_dis import PrtDis
from spec.ipkg.prt_prp import PrtPrp


class PrtModel(MFModel, Resolve):
    dis6 = PrtDis()
    prp6 = PrtPrp()
