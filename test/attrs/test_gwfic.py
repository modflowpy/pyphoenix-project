import numpy as np
from attr import define, field
from numpy.typing import NDArray


@define
class Options:
    export_array_ascii: bool = field(
        default=False,
        metadata={"longname": "export array variables to netcdf output files"},
    )
    """
    keyword that specifies input griddata arrays should be
    written to layered ascii output files.
    """

    export_array_netcdf: bool = field(
        default=False, metadata={"longname": "starting head"}
    )
    """
    keyword that specifies input griddata arrays should be
    written to the model output netcdf file.
    """


@define
class PackageData:
    strt: NDArray[np.float64] = field(
        metadata={"longname": "starting head", "shape": ("nodes")}
    )
    """
    is the initial (starting) head---that is, head at the
    beginning of the GWF Model simulation.  STRT must be specified for
    all simulations, including steady-state simulations. One value is
    read for every model cell. For simulations in which the first stress
    period is steady state, the values used for STRT generally do not
    affect the simulation (exceptions may occur if cells go dry and (or)
    rewet). The execution time, however, will be less if STRT includes
    hydraulic heads that are close to the steady-state solution.  A head
    value lower than the cell bottom can be provided if a cell should
    start as dry.
    """


@define
class GwfIc:
    options: Options = field()
    packagedata: PackageData = field()
