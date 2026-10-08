from pathlib import Path
from typing import TYPE_CHECKING

import xarray as xr
import xugrid as xu

from flopy4.mf6.utils import open_cbc, open_hds

if TYPE_CHECKING:
    from flopy4.mf6.gwf import Gwf


class GwfMethods:
    """Methods for the generated `Gwf`; fields come from the DFN."""

    class Output:
        """The model's head and budget output, read from its workspace."""

        def __init__(self, parent: "Gwf"):
            self.parent = parent

        def _grb_path(self) -> Path:
            """The binary grid file: the discretization's `grb_file`, or
            its input file's name with `.grb` appended, as MF6 names it."""
            dis = self.parent.dis
            grb_file = getattr(dis, "grb_file", None)
            if grb_file is not None:
                return self.parent.workspace / grb_file
            return Path(f"{dis.path}.grb")  # type: ignore[union-attr]

        @property
        def head(self) -> xr.DataArray | xu.UgridDataArray:
            path = self.parent.workspace

            hds_fpth = None
            head_file = self.parent.oc.head_file if self.parent.oc is not None else None
            if head_file is not None:
                fpth = path / head_file
                if fpth.exists():
                    hds_fpth = fpth

            if hds_fpth is None:
                # Check for output NC file configured on the model
                nc_fname = self.parent.netcdf_mesh2d_file or self.parent.netcdf_structured_file
                if nc_fname is not None:
                    fpth = path / nc_fname
                    if fpth.exists():
                        hds_fpth = fpth

            if hds_fpth is None:
                raise FileNotFoundError(f"No head file (*.hds, *.hed, *.nc) found in {path}")

            return open_hds(
                hds_fpth,
                self._grb_path(),
            )

        @property
        def budget(self) -> xr.Dataset | xu.UgridDataset:
            path = self.parent.workspace

            cbc_fpth = None
            cbc_file = self.parent.oc.budget_file if self.parent.oc is not None else None
            if cbc_file is not None:
                fpth = path / cbc_file
                if fpth.exists():
                    cbc_fpth = fpth

            if cbc_fpth is None:
                raise FileNotFoundError(f"No budget file (*.bud, *.cbc) found in {path}")

            return open_cbc(
                cbc_fpth,
                self._grb_path(),
            )

    @property
    def output(self: "Gwf") -> "GwfMethods.Output":  # type: ignore[misc]
        """The model's head and budget output."""
        return GwfMethods.Output(self)
