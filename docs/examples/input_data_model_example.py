# # Input data model
#
# FloPy organizes input variables in components: simulations, models,
# packages, and subpackages.
#
# The MODFLOW 6 data model is arranged in the following way:
#
# ```mermaid
# classDiagram
#     Simulation *-- "1+" Package
#     Simulation *-- "1+" Model
#     Simulation *-- "1+" Variable
#     Model *-- "1+" Package
#     Model *-- "1+" Subpackage
#     Model *-- "1+" Variable
#     Package *-- "1+" Subpackage
#     Package *-- "1+" Variable
# ```
#
# Components are generally mutable and variables can be manipulated at will.
#
# # Variable types
#
# Variables are generally scalars, arrays, or composite data types: list,
# sum, union.
#
# The variable type structure can be summarized briefly as:

# +
from os import PathLike
from typing import (
    Iterable,
    Tuple,
    Union,
)

from numpy.typing import ArrayLike

Scalar = Union[bool, int, float, str]
Path = PathLike
Array = ArrayLike
Record = Tuple[Union[Scalar, "Record"], ...]
Table = Iterable["Record"]
Variable = Union[Scalar, Array, Table, Record]
# -
