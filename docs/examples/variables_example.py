# Input variables
#
# TODO: flesh this out, describe prospective plan for type hints,
# determine whether we want to work directly with numpy or with
# e.g. xarray, etc. This will probably evolve for a while as we
# rework the prototype with c/attrs
#
# FloPy organizes input variables in components: simulations, models,
# packages, and subpackages.
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
# Note that this is not identical to the underlying object model, which
# is yet to be determined. TODO: update this once we have a full prototype.
#
# # Variable types
#
# Variables are scalars, paths, arrays, or composite types: list, sum, union.
#
# MODFLOW 6 defines the following scalar types:
#
# - `keyword`
# - `integer`
# - `double precision`
# - `string`
#
# And the following composites:
#
# - `record`: product type
# - `keystring`: union type
# - `recarray`: list type
#
# Scalars may (and `recarray` must) have a `shape`. If a scalar has a `shape`,
# its type becomes a homogeneous scalar array. A `recarray` may contain records
# or unions of records as items.
#
# We map this typology roughly to the following in Python:
#
# TODO: update the following as we develop a more concrete idea of what
# type hints corresponding to the mf6 input data model will look like

# +
from os import PathLike
from typing import (
    Any,
    Iterable,
    Tuple,
    Union,
)

from numpy.typing import ArrayLike
from pandas import DataFrame

Scalar = Union[bool, int, float, str]
Path = PathLike
Array = ArrayLike
Record = Tuple[Union[Scalar, "Record"], ...]
Table = Union[Iterable[Record], DataFrame]
List = Iterable[Any]
Variable = Union[Scalar, Array, Record, Table, List]
# -

# Note that:
#
# - Keystrings are omitted above, since a keystring simply becomes a
# `Union` of records or scalars.
# - List input may be regular (items all have the same record type) or
# irregular (items are unions of records).
# - A table is a special case of list input; since it is regular it can
# be represented as a dataframe.
# - While MODFLOW 6 typically formulates file path inputs as records with
# 3 fields (identifying keyword, `filein`/`fileout`, and filename), FloPy
# simply accepts `PathLike`.

# TODO: demonstrate setting/accessing scalars in an options block
