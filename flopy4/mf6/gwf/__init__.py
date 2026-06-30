from pathlib import Path
from typing import Optional, Union

import attrs
import xarray as xr
import xugrid as xu
from attrs import define
from flopy.discretization.grid import Grid
from flopy.discretization.structuredgrid import StructuredGrid
from flopy.discretization.vertexgrid import VertexGrid
from xattree import xattree

from flopy4.mf6.gwf.buy import Buy
from flopy4.mf6.gwf.chd import Chd
from flopy4.mf6.gwf.chdg import Chdg
from flopy4.mf6.gwf.csub import Csub
from flopy4.mf6.gwf.dis import Dis
from flopy4.mf6.gwf.disbase import DisBase
from flopy4.mf6.gwf.disv import Disv
from flopy4.mf6.gwf.drn import Drn
from flopy4.mf6.gwf.drng import Drng
from flopy4.mf6.gwf.evt import Evt
from flopy4.mf6.gwf.evta import Evta
from flopy4.mf6.gwf.ghb import Ghb
from flopy4.mf6.gwf.ghbg import Ghbg
from flopy4.mf6.gwf.ic import Ic
from flopy4.mf6.gwf.lak import Lak
from flopy4.mf6.gwf.mvr import Mvr
from flopy4.mf6.gwf.npf import Npf
from flopy4.mf6.gwf.oc import Oc
from flopy4.mf6.gwf.rch import Rch
from flopy4.mf6.gwf.rcha import Rcha
from flopy4.mf6.gwf.riv import Riv
from flopy4.mf6.gwf.rivg import Rivg
from flopy4.mf6.gwf.sto import Sto
from flopy4.mf6.gwf.vsc import Vsc
from flopy4.mf6.gwf.wel import Wel
from flopy4.mf6.gwf.welg import Welg
from flopy4.mf6.model import Model
from flopy4.mf6.spec import field, path
from flopy4.mf6.utils import open_cbc, open_hds
from flopy4.utils import to_path

__all__ = [
    "Gwf",
    "Buy",
    "Chd",
    "Chdg",
    "Dis",
    "Disv",
    "Drn",
    "Drng",
    "Evt",
    "Evta",
    "Ghb",
    "Ghbg",
    "Ic",
    "Csub",
    "Lak",
    "Npf",
    "Oc",
    "Rch",
    "Rcha",
    "Api",
    "Mvr",
    "Riv",
    "Rivg",
    "Sto",
    "Vsc",
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
        def head(self) -> xr.DataArray | xu.UgridDataArray:
            path = self.parent.workspace
            dis_ext = "disv" if isinstance(self.parent.dis, Disv) else "dis"

            hds_fpth = None
            head_file = self.parent.oc.head_file if self.parent.oc is not None else None
            if head_file is not None:
                fpth = path / Path(head_file).name
                if fpth.exists():
                    hds_fpth = fpth

            if hds_fpth is None:
                # Check for output NC file configured on the model
                nc_fname = self.parent.netcdf_mesh2d_file or self.parent.netcdf_structured_file
                if nc_fname is not None:
                    fpth = path / Path(nc_fname).name
                    if fpth.exists():
                        hds_fpth = fpth

            if hds_fpth is None:
                raise FileNotFoundError(f"No head file (*.hds, *.hed, *.nc) found in {path}")

            return open_hds(
                hds_fpth,
                self.parent.workspace / f"{self.parent.name}.{dis_ext}.grb",  # type: ignore
            )

        @property
        def budget(self) -> xr.Dataset | xu.UgridDataset:
            path = self.parent.workspace
            dis_ext = "disv" if isinstance(self.parent.dis, Disv) else "dis"

            cbc_fpth = None
            cbc_file = self.parent.oc.budget_file if self.parent.oc is not None else None
            if cbc_file is not None:
                fpth = path / Path(cbc_file).name
                if fpth.exists():
                    cbc_fpth = fpth

            if cbc_fpth is None:
                raise FileNotFoundError(f"No budget file (*.bud, *.cbc) found in {path}")

            return open_cbc(
                cbc_fpth,
                self.parent.workspace / f"{self.parent.name}.{dis_ext}.grb",  # type: ignore
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
    netcdf_input_file: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="filein"
    )
    dis: DisBase | None = field(converter=convert_grid, block="packages", default=None)
    ic: Ic | None = field(block="packages", default=None)
    oc: Oc | None = field(block="packages", default=None)
    npf: Npf | None = field(block="packages", default=None)
    sto: Sto | None = field(block="packages", default=None)
    buy: Buy | None = field(block="packages", default=None)
    chd: list[Union[Chd, Chdg]] = field(block="packages")
    drn: list[Union[Drn, Drng]] = field(block="packages")
    evt: list[Union[Evt, Evta]] = field(block="packages")
    ghb: list[Union[Ghb, Ghbg]] = field(block="packages")
    rch: list[Union[Rch, Rcha]] = field(block="packages")
    riv: list[Union[Riv, Rivg]] = field(block="packages")
    csub: list[Csub] = field(block="packages")
    lak: list[Lak] = field(block="packages")
    mvr: Mvr | None = field(block="packages", default=None)
    vsc: Vsc | None = field(block="packages", default=None)
    wel: list[Union[Wel, Welg]] = field(block="packages")
    output: Output = attrs.field(
        default=attrs.Factory(lambda self: Gwf.Output(self), takes_self=True)
    )

    @property
    def grid(self) -> Grid:
        if self.dis is not None:
            return self.dis.to_grid()
