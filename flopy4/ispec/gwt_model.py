# generated file
from flopy4.model import MFModel
from flopy4.resolver import Resolve
from flopy4.ispec.gwt_dis import GwtDis
from flopy4.ispec.gwt_disu import GwtDisu
from flopy4.ispec.gwt_disv import GwtDisv


class GwtModel(MFModel, Resolve):
    dis6 = GwtDis()
    disu6 = GwtDisu()
    disv6 = GwtDisv()
