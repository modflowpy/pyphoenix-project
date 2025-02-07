from pathlib import Path
from typing import Optional

from attr import define, field

from flopy4 import component, init_tree, setattribute
from flopy4.mf6 import Model
from flopy4.mf6.gwf.chd import Chd
from flopy4.mf6.gwf.dis import Dis
from flopy4.mf6.gwf.ic import Ic
from flopy4.mf6.gwf.npf import Npf
from flopy4.mf6.gwf.oc import Oc

__all__ = ["Gwf", "Chd", "Dis", "Ic", "Npf", "Oc"]


@component
@define(init=False, slots=False, on_setattr=setattribute)
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

    def __init__(
        self,
        sim=None,
        name=None,
        path=None,
        list=None,
        print_input=False,
        print_flows=False,
        save_flows=False,
        newtonoptions=None,
        nc_mesh2d_filerecord=None,
        nc_structured_filerecord=None,
        nc_filerecord=None,
    ):
        super().__init__(name, path)
        init_tree(
            self,
            parent=sim,
            list=list,
            print_input=print_input,
            print_flows=print_flows,
            save_flows=save_flows,
            newtonoptions=newtonoptions,
            nc_mesh2d_filerecord=nc_mesh2d_filerecord,
            nc_structured_filerecord=nc_structured_filerecord,
            nc_filerecord=nc_filerecord,
        )
