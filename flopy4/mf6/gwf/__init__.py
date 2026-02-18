from pathlib import Path
from typing import Optional, Union

import attrs
import xarray as xr
from attrs import define
from flopy.discretization.grid import Grid
from flopy.discretization.structuredgrid import StructuredGrid
from flopy.discretization.vertexgrid import VertexGrid
from xattree import xattree

from flopy4.mf6.gwf.chd import Chd
from flopy4.mf6.gwf.chdg import Chdg
from flopy4.mf6.gwf.dis import Dis
from flopy4.mf6.gwf.disbase import DisBase
from flopy4.mf6.gwf.disv import Disv
from flopy4.mf6.gwf.drn import Drn
from flopy4.mf6.gwf.drng import Drng
from flopy4.mf6.gwf.evta import Evta
from flopy4.mf6.gwf.ghb import Ghb
from flopy4.mf6.gwf.ic import Ic
from flopy4.mf6.gwf.npf import Npf
from flopy4.mf6.gwf.oc import Oc
from flopy4.mf6.gwf.rch import Rch
from flopy4.mf6.gwf.rcha import Rcha
from flopy4.mf6.gwf.sto import Sto
from flopy4.mf6.gwf.wel import Wel
from flopy4.mf6.gwf.welg import Welg
from flopy4.mf6.model import Model
from flopy4.mf6.spec import field, path
from flopy4.mf6.utils import open_cbc, open_hds
from flopy4.utils import to_path

__all__ = [
    "Gwf",
    "Chd",
    "Chdg",
    "Dis",
    "Disv",
    "Drn",
    "Drng",
    "Evta",
    "Ghb",
    "Ic",
    "Npf",
    "Oc",
    "Rch",
    "Rcha",
    "Sto",
    "Wel",
    "Welg",
]


def convert_grid(value):
    if isinstance(value, StructuredGrid):
        return Dis.from_grid(value)
    elif isinstance(value, VertexGrid):
        return Disv.from_grid(value)
    if isinstance(value, Dis):
        return value
    if isinstance(value, Disv):
        return value
    if value is None:
        return None
    raise TypeError(f"Expected Grid or Dis/Disv, got {type(value)}")


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
            dis_ext = "disv" if isinstance(self.parent.dis, Disv) else "dis"
            return open_hds(
                self.parent.parent.workspace / f"{self.parent.name}.hds",  # type: ignore
                self.parent.parent.workspace / f"{self.parent.name}.{dis_ext}.grb",  # type: ignore
            )

        @property
        def budget(self):
            # TODO support other extensions than .bud (e.g. .cbc)
            dis_ext = "disv" if isinstance(self.parent.dis, Disv) else "dis"
            return open_cbc(
                self.parent.parent.workspace / f"{self.parent.name}.bud",
                self.parent.parent.workspace / f"{self.parent.name}.{dis_ext}.grb",
            )

    _list: Optional[str] = field(block="options", default=None)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    newton: bool = field(block="options", default=False)
    newtonoptions: Optional[NewtonOptions] = field(block="options", default=None)
    netcdf_mesh2d_file: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="fileout"
    )
    netcdf_structured_file: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="fileout"
    )
    netcdf_file: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="filein"
    )
    dis: DisBase | None = field(converter=convert_grid, block="packages", default=None)
    ic: Ic | None = field(block="packages", default=None)
    oc: Oc | None = field(block="packages", default=None)
    npf: Npf | None = field(block="packages", default=None)
    sto: Sto | None = field(block="packages", default=None)
    chd: list[Union[Chd, Chdg]] = field(block="packages")
    drn: list[Union[Drn, Drng]] = field(block="packages")
    evt: list[Union[Evta]] = field(block="packages")
    ghb: list[Union[Ghb]] = field(block="packages")
    rch: list[Union[Rch, Rcha]] = field(block="packages")
    wel: list[Union[Wel, Welg]] = field(block="packages")
    output: Output = attrs.field(
        default=attrs.Factory(lambda self: Gwf.Output(self), takes_self=True)
    )

    @property
    def grid(self) -> Grid:
        if self.dis is not None:
            return self.dis.to_grid()
