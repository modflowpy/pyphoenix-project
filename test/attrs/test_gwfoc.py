from pathlib import Path
from typing import List, Literal, Optional, Union

from attr import asdict, define, field, fields_dict
from cattr import Converter

ArrayFormat = Literal["exponential", "fixed", "general", "scientific"]


@define
class PrintFormat:
    columns: int = field()
    """
    number of columns for writing data
    """

    width: int = field()
    """
    width for writing each number
    """

    digits: int = field()
    """
    number of digits to use for writing a number
    """

    array_format: ArrayFormat = field()
    """
    write format can be EXPONENTIAL, FIXED, GENERAL, or SCIENTIFIC
    """


@define
class Options:
    budget_file: Optional[Path] = field(default=None)
    """
    name of the output file to write budget information
    """

    budget_csv_file: Optional[Path] = field(default=None)
    """
    name of the comma-separated value (CSV) output 
    file to write budget summary information. 
    A budget summary record will be written to this 
    file for each time step of the simulation.
    """

    head_file: Optional[Path] = field(default=None)
    """
    name of the output file to write head information.
    """

    print_format: Optional[PrintFormat] = field(default=None)
    """
    specify format for printing to the listing file
    """


@define
class All:
    all: bool = field()
    """
    keyword to indicate save for all time steps in period.
    """


@define
class First:
    first: bool = field()
    """
    keyword to indicate save for first step in period.
    """


@define
class Last:
    last: bool = field()
    """
    keyword to indicate save for last step in period
    """


@define
class Steps:
    steps: List[int] = field()
    """
    save for each step specified
    """


@define
class Frequency:
    frequency: int = field()
    """
    save at the specified time step frequency.
    """


# It's awkward to have single-parameter contexts, but
# it's the only way I got `cattrs` to distinguish the
# choices in the union. There is likely a better way.


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
    """
    options block
    """

    periods: Periods = field()
    """
    period blocks
    """


# Converter

converter = Converter()


def output_control_data_hook(value, type) -> OutputControlData:
    return OutputControlData.from_tuple(value)


converter.register_structure_hook(OutputControlData, output_control_data_hook)


# Tests


def test_spec():
    spec = fields_dict(OutputControlData)
    assert len(spec) == 3

    ocsetting = spec["ocsetting"]
    assert ocsetting.type is OCSetting


def test_options_to_dict():
    options = Options(
        budget_file="some/file/path.cbc",
    )
    assert isinstance(options.budget_file, str)  # TODO path
    assert len(asdict(options)) == 4


def test_output_control_data_from_tuple():
    ocdata = OutputControlData.from_tuple(
        ("print", "budget", "steps", 1, 3, 5)
    )
    assert ocdata.printsave == "print"
    assert ocdata.rtype == "budget"
    assert ocdata.ocsetting == Steps([1, 3, 5])


def test_gwfoc_from_dict():
    gwfoc = converter.structure(
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
                    ("print", "budget", "steps", 1, 3, 5),
                    ("save", "head", "frequency", 2),
                ]
            ],
        },
        GwfOc,
    )
    assert gwfoc.options.budget_file == Path("some/file/path.cbc")
    assert gwfoc.options.print_format.width == 10
    assert gwfoc.options.print_format.array_format == "scientific"
    period = gwfoc.periods[0]
    assert len(period) == 2
    assert period[0] == OutputControlData.from_tuple(
        ("print", "budget", "steps", 1, 3, 5)
    )
