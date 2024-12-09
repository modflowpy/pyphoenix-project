# # Attrs demo

# This example demonstrates a tentative `attrs`-based object model.

from pathlib import Path
from typing import List, Literal, Optional

import numpy as np
from attr import asdict, define, field
from cattr import Converter
from flopy.discretization import StructuredGrid
from numpy.typing import NDArray
from xarray import Dataset, DataTree


@define
class GwfIc:
    strt: NDArray[np.float64] = field(
        metadata={"block": "packagedata", "shape": "(nodes)"}
    )
    export_array_ascii: bool = field(
        default=False, metadata={"block": "options"}
    )
    export_array_netcdf: bool = field(
        default=False,
        metadata={"block": "options"},
    )

    def __attrs_post_init__(self):
        # TODO: setup attributes for blocks?
        self.data = DataTree(Dataset({"strt": self.strt}), name="ic")


@define
class GwfOc:
    @define
    class Format:
        columns: int
        width: int
        digits: int
        format: Literal["exponential", "fixed", "general", "scientific"]

    periods: List[List[tuple]] = field(metadata={"block": "perioddata"})
    budget_file: Optional[Path] = field(
        default=None, metadata={"block": "options"}
    )
    budget_csv_file: Optional[Path] = field(
        default=None, metadata={"block": "options"}
    )
    head_file: Optional[Path] = field(
        default=None, metadata={"block": "options"}
    )
    printhead: Optional[Format] = field(
        default=None, metadata={"block": "options"}
    )


@define
class GwfDis:
    nlay: int = field(metadata={"block": "dimensions"})
    ncol: int = field(metadata={"block": "dimensions"})
    nrow: int = field(metadata={"block": "dimensions"})
    delr: NDArray[np.float64] = field(
        metadata={"block": "griddata", "shape": "(ncol,)"}
    )
    delc: NDArray[np.float64] = field(
        metadata={"block": "griddata", "shape": "(nrow,)"}
    )
    top: NDArray[np.float64] = field(
        metadata={"block": "griddata", "shape": "(ncol, nrow)"}
    )
    botm: NDArray[np.float64] = field(
        metadata={"block": "griddata", "shape": "(ncol, nrow, nlay)"}
    )
    idomain: NDArray[np.float64] = field(
        metadata={"block": "griddata", "shape": "(ncol, nrow, nlay)"}
    )
    length_units: str = field(default=None, metadata={"block": "options"})
    nogrb: bool = field(default=False, metadata={"block": "options"})
    xorigin: float = field(default=None, metadata={"block": "options"})
    yorigin: float = field(default=None, metadata={"block": "options"})
    angrot: float = field(default=None, metadata={"block": "options"})
    export_array_netcdf: bool = field(
        default=False, metadata={"block": "options"}
    )

    def __attrs_post_init__(self):
        self.data = DataTree(
            Dataset(
                {
                    "nlay": self.nlay,
                    "ncol": self.ncol,
                    "nrow": self.nrow,
                    "delr": self.delr,
                    "delc": self.delc,
                    "top": self.top,
                    "botm": self.botm,
                    "idomain": self.idomain,
                }
            ),
            name="dis",
        )
        # TODO: check for parent and update dimensions
        # then try to realign any existing packages?


@define
class Gwf:
    dis: GwfDis = field()
    ic: GwfIc = field()

    def __attrs_post_init__(self):
        self.data = DataTree.from_dict(
            {"/dis": self.dis, "/ic": self.ic}, name="gwf"
        )
        self.grid = StructuredGrid(**asdict(self.dis))

    @ic.validator
    def _check_dims(self, attribute, value):
        assert value.strt.shape == (
            self.dis.nlay * self.dis.nrow * self.dis.ncol
        )


# We can define a package with some data.


oc = GwfOc(
    budget_file="some/file/path.cbc",
    periods=[[("print", "budget", "steps", 1, 3, 5)]],
)
assert isinstance(oc.budget_file, str)  # TODO path


# We now set up a `cattrs` converter to convert an unstructured
# representation of the package input data to a structured form.

converter = Converter()


# We can load the full package from an unstructured dictionary,
# as would be returned by a separate IO layer in the future.
# (Either hand-written or using e.g. lark.)

gwfoc = converter.structure(
    {
        "budget_file": "some/file/path.cbc",
        "head_file": "some/file/path.hds",
        "printhead": {
            "columns": 1,
            "width": 10,
            "digits": 8,
            "format": "scientific",
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
assert gwfoc.budget_file == Path("some/file/path.cbc")
assert gwfoc.printhead.width == 10
assert gwfoc.printhead.format == "scientific"
period = gwfoc.periods[0]
assert len(period) == 2
assert period[0] == ("print", "budget", "steps", 1, 3, 5)
