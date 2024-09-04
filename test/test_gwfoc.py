from pathlib import Path
from typing import Dict, List, Literal, Optional, Union

from cattrs import unstructure

from flopy4.attrs import context, is_frozen, param, params, to_path

# Define the package input specification.
# Some of this will be generic, and come
# from elsewhere, eventually.

ArrayFormat = Literal["exponential", "fixed", "general", "scientific"]


@context
class PrintFormat:
    columns: int = param(
        description="""
number of columns for writing data"""
    )
    width: int = param(
        description="""
width for writing each number"""
    )
    digits: int = param(
        description="""
number of digits to use for writing a number"""
    )
    array_format: ArrayFormat = param(
        description="""
write format can be EXPONENTIAL, FIXED, GENERAL, or SCIENTIFIC"""
    )


@context
class All:
    all: bool = param(
        description="""
keyword to indicate save for all time steps in period."""
    )


@context
class First:
    first: bool = param(
        description="""
keyword to indicate save for first step in period."""
    )


@context
class Last:
    last: bool = param(
        description="""
keyword to indicate save for last step in period"""
    )


@context
class Steps:
    steps: List[int] = param(
        description="""
save for each step specified."""
    )


@context
class Frequency:
    frequency: int = param(
        description="""
save at the specified time step frequency."""
    )


# It's awkward to have single-parameter contexts, but
# it's the only way I got `cattrs` to distinguish the
# choices in the union.


StepSelection = Union[All, First, Last, Steps, Frequency]
OutputAction = Literal["print", "save"]
OutputVariable = Literal["budget", "head"]


@context
class OutputControlData:
    action: OutputAction = param()
    variable: OutputVariable = param()
    ocsetting: StepSelection = param()


@context
class Options:
    budget_file: Optional[Path] = param(
        description="""
name of the output file to write budget information""",
        converter=to_path,
        default=None,
    )
    budget_csv_file: Optional[Path] = param(
        description="""
name of the comma-separated value (CSV) output 
file to write budget summary information. 
A budget summary record will be written to this 
file for each time step of the simulation.""",
        converter=to_path,
        default=None,
    )
    head_file: Optional[Path] = param(
        description="""
name of the output file to write head information.""",
        converter=to_path,
        default=None,
    )
    print_format: Optional[PrintFormat] = param(
        description="""
specify format for printing to the listing file""",
        default=None,
    )


Period = List[OutputControlData]
Periods = List[Period]


@context
class GwfOc:
    options: Options = param(
        description="""
options block"""
    )
    periods: Periods = param(
        description="""
period blocks"""
    )


# Tests


def test_spec():
    spec = params(OutputControlData)
    assert len(spec) == 3
    assert isinstance(spec, Dict)
    assert not is_frozen(OutputControlData)

    ocsetting = spec["ocsetting"]
    assert ocsetting.type is StepSelection


def test_options():
    options = Options(
        budget_file="some/file/path.cbc",
    )
    assert isinstance(options.budget_file, Path)
    assert len(unstructure(options)) == 4


def test_gwfoc_structure():
    gwfoc = GwfOc.from_dict(
        {
            "options": {
                "budget_file": "some/file/path.cbc",
                "head_file": "some/file/path.hds",
                "print_format": {
                    "columns": 1,
                    "width": 10,
                    "digits": 8,
                    "array_format": "scientific",
                },
            },
            "periods": [
                [
                    {
                        "action": "print",
                        "variable": "budget",
                        "ocsetting": {"steps": [1, 3, 5]},
                    },
                    {
                        "action": "save",
                        "variable": "head",
                        "ocsetting": {"frequency": 2},
                    },
                ]
            ],
        }
    )
    assert gwfoc.options.budget_file == Path("some/file/path.cbc")
    assert gwfoc.options.print_format.width == 10
    assert gwfoc.options.print_format.array_format == "scientific"
    period = gwfoc.periods[0]
    assert len(period) == 2
    assert period[0] == OutputControlData(
        action="print", variable="budget", ocsetting=Steps([1, 3, 5])
    )
