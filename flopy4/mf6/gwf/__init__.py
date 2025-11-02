from pathlib import Path
from typing import Optional

import attrs
import xarray as xr
from attrs import define
from flopy.discretization.grid import Grid
from xattree import xattree

from flopy4.mf6.gwf.chd import Chd
from flopy4.mf6.gwf.dis import Dis
from flopy4.mf6.gwf.drn import Drn
from flopy4.mf6.gwf.ic import Ic
from flopy4.mf6.gwf.npf import Npf
from flopy4.mf6.gwf.oc import Oc
from flopy4.mf6.gwf.sto import Sto
from flopy4.mf6.gwf.wel import Wel
from flopy4.mf6.model import Model
from flopy4.mf6.spec import field, path
from flopy4.mf6.utils import open_cbc, open_hds
from flopy4.utils import to_path

__all__ = ["Gwf", "Chd", "Dis", "Drn", "Ic", "Npf", "Oc", "Sto", "Wel"]


def convert_grid(value):
    if isinstance(value, Grid):
        return Dis.from_grid(value)
    if isinstance(value, Dis):
        return value
    raise TypeError(f"Expected Grid or Dis, got {type(value)}")


@xattree
class Gwf(Model):
    @define
    class NewtonOptions:
        newton: bool = field()
        under_relaxation: bool = field()

    @define
    class Output:
        parent: "Gwf" = attrs.field(repr=False)

        @property
        def head(self) -> xr.DataArray:
            # TODO support other extensions than .hds (e.g. .hed)
            return open_hds(
                self.parent.parent.workspace / f"{self.parent.name}.hds",  # type: ignore
                self.parent.parent.workspace / f"{self.parent.name}.dis.grb",  # type: ignore
            )

        @property
        def budget(self):
            # TODO support other extensions than .bud (e.g. .cbc)
            return open_cbc(
                self.parent.parent.workspace / f"{self.parent.name}.bud",
                self.parent.parent.workspace / f"{self.parent.name}.dis.grb",
            )

    _list: Optional[str] = field(block="options", default=None)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    newtonoptions: Optional[NewtonOptions] = field(block="options", default=None)
    nc_mesh2d_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="fileout"
    )
    nc_structured_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="fileout"
    )
    nc_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="fileout"
    )
    dis: Dis = field(converter=convert_grid, block="packages")
    ic: Ic | None = field(block="packages", default=None)
    oc: Oc | None = field(block="packages", default=None)
    npf: Npf | None = field(block="packages", default=None)
    sto: Sto | None = field(block="packages", default=None)
    chd: list[Chd] = field(block="packages")
    wel: list[Wel] = field(block="packages")
    drn: list[Drn] = field(block="packages")
    output: Output = attrs.field(
        default=attrs.Factory(lambda self: Gwf.Output(self), takes_self=True)
    )

    @property
    def grid(self) -> Grid:
        return self.dis.to_grid()
