from pathlib import Path
from typing import Optional

from attr import define, field

from flopy4 import component, setattribute
from flopy4.mf6 import Model
from flopy4.mf6.gwf.chd import Chd
from flopy4.mf6.gwf.dis import Dis
from flopy4.mf6.gwf.ic import Ic
from flopy4.mf6.gwf.npf import Npf
from flopy4.mf6.gwf.oc import Oc

__all__ = ["Gwf", "Chd", "Dis", "Ic", "Npf", "Oc"]


@component
@define(slots=False, on_setattr=setattribute)
class Gwf(Model):
    @define(slots=False)
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
