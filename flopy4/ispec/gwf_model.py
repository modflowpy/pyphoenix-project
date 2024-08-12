# generated file
from flopy4.model import MFModel
from flopy4.resolver import Resolve
from flopy4.ispec.gwf_dis import GwfDis
from flopy4.ispec.gwf_ic import GwfIc
from flopy4.ispec.gwf_nam import GwfNam


class GwfModel(MFModel, Resolve):
    dis6 = GwfDis()
    ic6 = GwfIc()
    nam6 = GwfNam()
