from pathlib import Path
from typing import ClassVar, Optional

from xattree import xattree

from flopy4.mf6.solution import Solution
from flopy4.mf6.spec import field, path
from flopy4.utils import to_path


@xattree
class Ims(Solution):
    slntype: ClassVar[str] = "ims"

    print_option: Optional[str] = field(block="options", default=None)
    complexity: str = field(block="options", default="simple")
    csv_outer_output_file: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="fileout"
    )
    csv_inner_output_file: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="fileout"
    )
    no_ptc: bool = field(block="options", default=False)
    no_ptc_option: Optional[str] = field(block="options", default=None)
    ats_outer_maximum_fraction: Optional[float] = field(block="options", default=None)
    outer_dvclose: Optional[float] = field(block="nonlinear", default=None)
    outer_maximum: Optional[int] = field(block="nonlinear", default=None)
    under_relaxation: Optional[str] = field(block="nonlinear", default=None)
    under_relaxation_gamma: Optional[float] = field(block="nonlinear", default=None)
    under_relaxation_theta: Optional[float] = field(block="nonlinear", default=None)
    under_relaxation_kappa: Optional[float] = field(block="nonlinear", default=None)
    under_relaxation_momentum: Optional[float] = field(block="nonlinear", default=None)
    backtracking_tolerance: Optional[float] = field(block="nonlinear", default=None)
    backtracking_reduction_factor: Optional[float] = field(block="nonlinear", default=None)
    backtracking_residual_limit: Optional[float] = field(block="nonlinear", default=None)
    inner_maximum: Optional[int] = field(block="linear", default=None)
    inner_dvclose: Optional[float] = field(block="linear", default=None)
    inner_rclose: Optional[float] = field(block="linear", default=None)
    inner_hclose: Optional[float] = field(block="linear", default=None)
    rclose_option: Optional[str] = field(block="linear", default=None)
    linear_acceleration: Optional[str] = field(block="linear", default=None)
    relaxation_factor: Optional[float] = field(block="linear", default=None)
    preconditioner_levels: Optional[int] = field(block="linear", default=None)
    preconditioner_drop_tolerance: Optional[float] = field(block="linear", default=None)
    number_orthogonalizations: Optional[int] = field(block="linear", default=None)
    scaling_method: Optional[str] = field(block="linear", default=None)
    reordering_method: Optional[str] = field(block="linear", default=None)
