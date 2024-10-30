# generated file
from flopy4.model import MFModel
from flopy4.resolver import Resolve
from flopy4.ispec.gwf_chd import GwfChd
from flopy4.ispec.gwf_dis import GwfDis
from flopy4.ispec.gwf_disu import GwfDisu
from flopy4.ispec.gwf_disv import GwfDisv
from flopy4.ispec.gwf_ic import GwfIc
from flopy4.ispec.gwf_nam import GwfNam
from flopy4.ispec.gwf_npf import GwfNpf


class GwfModel(MFModel, Resolve):
    chd6 = GwfChd()
    dis6 = GwfDis()
    disu6 = GwfDisu()
    disv6 = GwfDisv()
    ic6 = GwfIc()
    nam6 = GwfNam()
    npf6 = GwfNpf()
