from pathlib import Path
from typing import Optional

from xattree import field, xattree

from flopy4.mf6.solution import Solution


@xattree
class Ims(Solution):
    print_option: bool = field(default=False, metadata={"block": "options"})
    complexity: str = field(default="simple", metadata={"block": "options"})
    csv_outer_output_file: Optional[Path] = field(
        default=None, metadata={"block": "options"}
    )
    csv_inner_output_file: Optional[Path] = field(
        default=None, metadata={"block": "options"}
    )
    no_ptc: bool = field(default=False, metadata={"block": "options"})
    no_ptc_option: Optional[str] = field(
        default=None, metadata={"block": "options"}
    )
    ats_outer_maximum_fraction: Optional[float] = field(
        default=None, metadata={"block": "options"}
    )
    outer_dvclose: Optional[float] = field(
        default=None, metadata={"block": "options"}
    )
    outer_maximum: Optional[int] = field(
        default=None, metadata={"block": "options"}
    )
    under_relaxation: Optional[str] = field(
        default=None, metadata={"block": "options"}
    )
    under_relaxation_gamma: Optional[float] = field(
        default=None, metadata={"block": "nonlinear"}
    )
    under_relaxation_theta: Optional[float] = field(
        default=None, metadata={"block": "nonlinear"}
    )
    under_relaxation_kappa: Optional[float] = field(
        default=None, metadata={"block": "nonlinear"}
    )
    under_relaxation_momentum: Optional[float] = field(
        default=None, metadata={"block": "nonlinear"}
    )
    backtracking_tolerance: Optional[float] = field(
        default=None, metadata={"block": "nonlinear"}
    )
    backtracking_reduction_factor: Optional[float] = field(
        default=None, metadata={"block": "nonlinear"}
    )
    backtracking_residual_limit: Optional[float] = field(
        default=None, metadata={"block": "nonlinear"}
    )
    inner_maximum: Optional[int] = field(
        default=None, metadata={"block": "linear"}
    )
    inner_dvclose: Optional[float] = field(
        default=None, metadata={"block": "linear"}
    )
    inner_rclose: Optional[float] = field(
        default=None, metadata={"block": "linear"}
    )
    rclose_option: Optional[str] = field(
        default=None, metadata={"block": "linear"}
    )
    linear_acceleration: Optional[str] = field(
        default=None, metadata={"block": "linear"}
    )
    relaxation_factor: Optional[float] = field(
        default=None, metadata={"block": "linear"}
    )
    preconditioner_levels: Optional[int] = field(
        default=None, metadata={"block": "linear"}
    )
    preconditioner_drop_tolerance: Optional[float] = field(
        default=None, metadata={"block": "linear"}
    )
    number_orthogonalizations: Optional[int] = field(
        default=None, metadata={"block": "linear"}
    )
    scaling_method: Optional[str] = field(
        default=None, metadata={"block": "linear"}
    )
    reordering_method: Optional[str] = field(
        default=None, metadata={"block": "linear"}
    )
