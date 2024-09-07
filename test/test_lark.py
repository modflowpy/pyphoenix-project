from os import linesep
from pathlib import Path

import numpy as np

from flopy4.mf6.io import MF6Transformer
from flopy4.mf6.io import make_parser as make_mf6_parser
from flopy4.mf6.io.spec import DFNTransformer
from flopy4.mf6.io.spec import make_parser as make_dfn_parser

COMPONENT = """
BEGIN OPTIONS
  K
  I 1
  D 1.0
  S hello world
  F FILEIN some/path
END OPTIONS

BEGIN PACKAGEDATA
  A INTERNAL 1.0 2.0 3.0
END PACKAGEDATA

BEGIN PERIOD 1
  FIRST
  FREQUENCY 2
END PERIOD 1

BEGIN PERIOD 2
  STEPS 1 2 3
END PERIOD 2
"""


MF6_PARSER = make_mf6_parser(
    params=["k", "i", "d", "s", "f", "a"],
    dict_blocks=["options", "packagedata"],
    list_blocks=["period"],
)
MF6_TRANSFORMER = MF6Transformer()


def test_parse_mf6():
    tree = MF6_PARSER.parse(COMPONENT)
    # view the parse tree with e.g.
    #   pytest test/test_lark.py::test_parse -s
    print(linesep + tree.pretty())


def test_transform_mf6():
    tree = MF6_PARSER.parse(COMPONENT)
    data = MF6_TRANSFORMER.transform(tree)
    assert data["options"] == {
        "d": 1.0,
        "f": Path("some/path"),
        "i": 1,
        "k": True,
        "s": "hello world",
    }
    assert np.array_equal(data["packagedata"]["a"], np.array([1.0, 2.0, 3.0]))
    assert data["period 1"][0] == ("FIRST",)
    assert data["period 1"][1] == ("FREQUENCY", 2)
    assert data["period 2"][0] == ("STEPS", 1, 2, 3)


DFN_PARSER = make_dfn_parser()
DFN_TRANSFORMER = DFNTransformer()

PROJ_ROOT = Path(__file__).parents[1]
DFNS_PATH = PROJ_ROOT / "spec" / "dfn"
DFN_PATH = DFNS_PATH / "gwf-ic.dfn"


def test_parse_dfn():
    tree = DFN_PARSER.parse(open(DFN_PATH).read())
    print(tree.pretty())


def test_transform_dfn():
    tree = DFN_PARSER.parse(open(DFN_PATH).read())
    data = DFN_TRANSFORMER.transform(tree)
    assert data["options"] == {
        "export_array_ascii": {
            "description": "keyword that specifies "
            "input griddata arrays "
            "should be written to "
            "layered ascii output "
            "files.",
            "longname": "export array variables to " "layered ascii files.",
            "mf6internal": "export_ascii",
            "name": "export_array_ascii",
            "optional": "true",
            "reader": "urword",
            "type": "keyword",
        },
        "export_array_netcdf": {
            "description": "keyword that specifies "
            "input griddata arrays "
            "should be written to the "
            "model output netcdf file.",
            "longname": "export array variables to " "netcdf output files.",
            "mf6internal": "export_nc",
            "name": "export_array_netcdf",
            "optional": "true",
            "reader": "urword",
            "type": "keyword",
        },
    }
    assert data["griddata"] == {
        "strt": {
            "default_value": "1.0",
            "description": "is the initial (starting) head---that "
            "is, head at the beginning of the GWF "
            "Model simulation. STRT must be "
            "specified for all simulations, "
            "including steady-state simulations. One "
            "value is read for every model cell. For "
            "simulations in which the first stress "
            "period is steady state, the values used "
            "for STRT generally do not affect the "
            "simulation (exceptions may occur if "
            "cells go dry and (or) rewet). The "
            "execution time, however, will be less "
            "if STRT includes hydraulic heads that "
            "are close to the steady-state solution. "
            "A head value lower than the cell bottom "
            "can be provided if a cell should start "
            "as dry.",
            "layered": "true",
            "longname": "starting head",
            "name": "strt",
            "reader": "readarray",
            "shape": "(nodes)",
            "type": "double precision",
        }
    }
