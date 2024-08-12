# generated file
from flopy4.model import MFModel
from flopy4.resolver import Resolve
from flopy4.ispec.prt_dis import PrtDis
from flopy4.ispec.prt_prp import PrtPrp


class PrtModel(MFModel, Resolve):
    dis6 = PrtDis()
    prp6 = PrtPrp()
