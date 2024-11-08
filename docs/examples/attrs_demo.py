# # Attrs demo

# This example demonstrates a tentative `attrs`-based object model.

from pathlib import Path
from typing import List, Literal, Optional, Union

# ## GWF IC
import numpy as np
from attr import asdict, define, field, fields_dict
from cattr import Converter
from numpy.typing import NDArray

# We can define block classes where variable descriptions become
# the variable's docstring. Ideally we can come up with a Python
# input specification that is equivalent to (and convertible to)
# the original MF6 input specification, while knowing as little
# as possible about the MF6 input format; but anything we can't
# get rid of can go in field `metadata`.


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


# Eventually we may be able to take advantage of NumPy
# support for shape parameters:
# https://github.com/numpy/numpy/issues/16544
#
# We can still take advantage of type parameters.


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


# Putting it all together:


@define
class GwfIc:
    options: Options = field()
    packagedata: PackageData = field()


# ## GWF OC
#
# The output control package has a more complicated variable structure.
# Below docstrings/descriptions are omitted for space-saving.


@define
class Format:
    columns: int = field()
    width: int = field()
    digits: int = field()
    format: Literal["exponential", "fixed", "general", "scientific"] = field()


@define
class Options:
    budget_file: Optional[Path] = field(default=None)
    budget_csv_file: Optional[Path] = field(default=None)
    head_file: Optional[Path] = field(default=None)
    printhead: Optional[Format] = field(default=None)


# It's awkward to have single-parameter classes, but
# it's the only way I got `cattrs` to distinguish a
# number of choices with the same shape in a union
# like `OCSetting`. There may be a better way.


@define
class All:
    all: bool = field()


@define
class First:
    first: bool = field()


@define
class Last:
    last: bool = field()


@define
class Steps:
    steps: List[int] = field()


@define
class Frequency:
    frequency: int = field()


PrintSave = Literal["print", "save"]
RType = Literal["budget", "head"]
OCSetting = Union[All, First, Last, Steps, Frequency]


@define
class OutputControlData:
    printsave: PrintSave = field()
    rtype: RType = field()
    ocsetting: OCSetting = field()

    @classmethod
    def from_tuple(cls, t):
        t = list(t)
        printsave = t.pop(0)
        rtype = t.pop(0)
        ocsetting = {
            "all": All,
            "first": First,
            "last": Last,
            "steps": Steps,
            "frequency": Frequency,
        }[t.pop(0).lower()](t)
        return cls(printsave, rtype, ocsetting)


Period = List[OutputControlData]
Periods = List[Period]


@define
class GwfOc:
    options: Options = field()
    periods: Periods = field()


# We now set up a `cattrs` converter to convert an unstructured
# representation of the package input data to a structured form.

converter = Converter()


# Register a hook for the `OutputControlData.from_tuple` method.
# MODFLOW 6 defines records as tuples, from which we'll need to
# instantiate objects.


def output_control_data_hook(value, _) -> OutputControlData:
    return OutputControlData.from_tuple(value)


converter.register_structure_hook(OutputControlData, output_control_data_hook)


# We can inspect the input specification with `attrs` machinery.


spec = fields_dict(OutputControlData)
assert len(spec) == 3

ocsetting = spec["ocsetting"]
assert ocsetting.type is OCSetting


# We can define a block with some data.


options = Options(
    budget_file="some/file/path.cbc",
)
assert isinstance(options.budget_file, str)  # TODO path
assert len(asdict(options)) == 4


# We can load a record from a tuple.


ocdata = OutputControlData.from_tuple(("print", "budget", "steps", 1, 3, 5))
assert ocdata.printsave == "print"
assert ocdata.rtype == "budget"
assert ocdata.ocsetting == Steps([1, 3, 5])


# We can load the full package from an unstructured dictionary,
# as would be returned by a separate IO layer in the future.
# (Either hand-written or using e.g. lark.)


gwfoc = converter.structure(
    {
        "options": {
            "budget_file": "some/file/path.cbc",
            "head_file": "some/file/path.hds",
            "printhead": {
                "columns": 1,
                "width": 10,
                "digits": 8,
                "format": "scientific",
            },
        },
        "periods": [
            [
                ("print", "budget", "steps", 1, 3, 5),
                ("save", "head", "frequency", 2),
            ]
        ],
    },
    GwfOc,
)
assert gwfoc.options.budget_file == Path("some/file/path.cbc")
assert gwfoc.options.printhead.width == 10
assert gwfoc.options.printhead.format == "scientific"
period = gwfoc.periods[0]
assert len(period) == 2
assert period[0] == OutputControlData.from_tuple(
    ("print", "budget", "steps", 1, 3, 5)
)
