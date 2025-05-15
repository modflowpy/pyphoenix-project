from pathlib import Path
from typing import Optional

import attrs
import imod
import xarray as xr
from attrs import define
from flopy.discretization.grid import Grid
from xattree import field, xattree

from flopy4.mf6.gwf.chd import Chd
from flopy4.mf6.gwf.dis import Dis
from flopy4.mf6.gwf.ic import Ic
from flopy4.mf6.gwf.npf import Npf
from flopy4.mf6.gwf.oc import Oc
from flopy4.mf6.model import Model
from flopy4.mf6.utils import open_hds

__all__ = ["Gwf", "Chd", "Dis", "Ic", "Npf", "Oc"]


def convert_grid(value):
    if isinstance(value, Grid):
        return Dis.from_grid(value)
    if isinstance(value, Dis):
        return value
    raise TypeError(f"Expected Grid or Dis, got {type(value)}")


@xattree
class Gwf(Model):
    @define
    class Output:
        parent: "Gwf" = attrs.field(repr=False)

        @property
        def head(self) -> xr.DataArray:
            return open_hds(
                self.parent.parent.sim_ws / f"{self.parent.name}.hds",  # type: ignore
                self.parent.parent.sim_ws / f"{self.parent.name}.dis.grb",  # type: ignore
            )

        @property
        def budget(self):
            return imod.mf6.open_cbc(
                self.parent.parent.sim_ws / "mymodel.bud",
                self.parent.parent.sim_ws / "mymodel.dis.grb",
                merge_to_dataset=True,
            )

    dis: Dis = field(converter=convert_grid)
    ic: Ic = field()
    oc: Oc = field()
    npf: Npf = field()
    chd: list[Chd] = field()
    output: Output = attrs.field(
        default=attrs.Factory(lambda self: Gwf.Output(self), takes_self=True)
    )

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

    @property
    def grid(self) -> Grid:
        return self.dis.to_grid()
