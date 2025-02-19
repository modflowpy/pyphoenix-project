from pathlib import Path
from typing import Optional

from attr import field
from attrs import define
from xattree import child, xattree

from flopy4.mf6 import Model
from flopy4.mf6.gwf.chd import Chd
from flopy4.mf6.gwf.dis import Dis
from flopy4.mf6.gwf.ic import Ic
from flopy4.mf6.gwf.npf import Npf
from flopy4.mf6.gwf.oc import Oc

__all__ = ["Gwf", "Chd", "Dis", "Ic", "Npf", "Oc"]


@xattree
class Gwf(Model):
    # "bind" indicates this is a subcomponent, not a variable.
    # TODO: add separate `component()` decorator like `field`?
    dis: Dis = child(Dis)
    ic: Ic = child(Dis)
    oc: Oc = child(Oc)
    npf: Npf = child(Npf)

    @define
    class NewtonOptions:
        newton: bool = field()
        under_relaxation: bool = field()

    list: Optional[str] = field(default=None, metadata={"block": "options"})
    print_input: bool = field(default=False, metadata={"block": "options"})
    print_flows: bool = field(default=False, metadata={"block": "options"})
    save_flows: bool = field(default=False, metadata={"block": "options"})
    newtonoptions: Optional[NewtonOptions] = field(
        default=None, metadata={"block": "options"}
    )
    nc_mesh2d_filerecord: Optional[Path] = field(
        default=None, metadata={"block": "options"}
    )
    nc_structured_filerecord: Optional[Path] = field(
        default=None, metadata={"block": "options"}
    )
    nc_filerecord: Optional[Path] = field(
        default=None, metadata={"block": "options"}
    )
