# generated file
from flopy4.model import MFModel
from flopy4.resolver import Resolve
from spec.ipkg.gwf_dis import GwfDis
from spec.ipkg.gwf_ic import GwfIc
from spec.ipkg.gwf_nam import GwfNam


class GwfModel(MFModel, Resolve):
    dis6 = GwfDis()
    ic6 = GwfIc()
    nam6 = GwfNam()
