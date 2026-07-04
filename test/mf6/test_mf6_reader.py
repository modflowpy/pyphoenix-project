"""Test the MF6 input file reader as implemented with lark."""

import os
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
from lark import Lark
from modflow_devtools.dfn import Dfn
from modflow_devtools.download import download_and_unzip
from packaging.version import Version

from flopy4.mf6.codec.reader.parser import get_typed_parser
from flopy4.mf6.codec.reader.transformer import TypedTransformer

PROJ_ROOT_PATH = Path(__file__).parents[2]
BASE_GRAMMAR_PATH = (
    PROJ_ROOT_PATH / "flopy4" / "mf6" / "codec" / "reader" / "grammar" / "typed.lark"
)


def typed_parser(grammar: str):
    with open(BASE_GRAMMAR_PATH, "r") as f:
        return Lark(grammar + os.linesep + f.read(), parser="lalr", debug=True)


def test_parse_internal_array():
    parser = typed_parser("start: array")
    tree = parser.parse("""
INTERNAL FACTOR 1.0 IPRN 3
1.2 3.7 9.3 4.2 2.2 9.9 1.0
3.3 4.9 7.3 7.5 8.2 8.7 6.6
4.5 5.7 2.2 1.1 1.7 6.7 6.9
7.4 3.5 7.8 8.5 7.4 6.8 8.8
    """)
    print(tree.pretty())
    assert len(tree.children) == 1
    array = tree.children[0]
    assert str(array.data) == "array"
    readarray = array.children[0].children[-1]
    assert str(readarray.data) == "readarray"
    control = readarray.children[0]
    assert str(control.data) == "control"
    internal = control.children[0]
    assert str(internal.data) == "internal"
    assert len(internal.children) == 2
    factor = internal.children[0]
    assert str(factor.data) == "factor"
    assert str(factor.children[0].data) == "double"
    assert float(factor.children[0].children[0]) == 1.0
    iprn = internal.children[1]
    assert str(iprn.data) == "iprn"
    assert str(iprn.children[0].data) == "integer"
    assert int(iprn.children[0].children[0]) == 3
    data = readarray.children[-1]
    assert len(data.children) == 28
    assert str(data.children[0].data) == "double"
    assert str(data.children[-1].data) == "double"
    assert float(data.children[0].children[0]) == 1.2
    assert float(data.children[-1].children[0]) == 8.8


def test_parse_layered_array():
    parser = typed_parser("start: array")
    tree = parser.parse("""
LAYERED
CONSTANT 1.0
INTERNAL FACTOR 1.0 IPRN 3
1.2 3.7 9.3 4.2 2.2 9.9 1.0
3.3 4.9 7.3 7.5 8.2 8.7 6.6
4.5 5.7 2.2 1.1 1.7 6.7 6.9
7.4 3.5 7.8 8.5 7.4 6.8 8.8
    """)
    print(tree.pretty())
    assert len(tree.children) == 1
    array = tree.children[0]
    assert str(array.data) == "array"
    layered_array = array.children[0]
    assert str(layered_array.data) == "layered_array"
    assert len(layered_array.children) == 4  # 2nd item is optional netcdf
    layered = layered_array.children[0]
    assert str(layered.data) == "layered"
    layer1 = layered_array.children[-2]
    assert str(layer1.data) == "readarray"
    control1 = layer1.children[0]
    assert str(control1.data) == "control"
    constant = control1.children[0]
    assert str(constant.data) == "constant"
    assert str(constant.children[0].data) == "double"
    assert float(constant.children[0].children[0]) == 1.0
    layer2 = layered_array.children[-1]
    assert str(layer2.data) == "readarray"
    control2 = layer2.children[0]
    assert str(control2.data) == "control"
    internal = control2.children[0]
    assert str(internal.data) == "internal"
    factor = internal.children[0]
    assert str(factor.data) == "factor"
    assert float(factor.children[0].children[0]) == 1.0
    iprn = internal.children[1]
    assert str(iprn.data) == "iprn"
    assert int(iprn.children[0].children[0]) == 3
    data = layer2.children[1]
    assert len(data.children) == 28
    assert float(data.children[0].children[0]) == 1.2
    assert float(data.children[-1].children[0]) == 8.8


def test_parse_constant_array():
    parser = typed_parser("start: array")
    tree = parser.parse("""
CONSTANT 1.0
    """)
    print(tree.pretty())
    assert len(tree.children) == 1
    array = tree.children[0]
    assert str(array.data) == "array"
    single_array = array.children[0]
    assert str(single_array.data) == "single_array"
    readarray = single_array.children[-1]  # optional netcdf comes first
    assert str(readarray.data) == "readarray"
    control = readarray.children[0]
    assert str(control.data) == "control"
    constant = control.children[0]
    assert str(constant.data) == "constant"
    assert str(constant.children[0].data) == "double"
    assert float(constant.children[0].children[0]) == 1.0


def test_parse_external_array_no_quotation_marks():
    parser = typed_parser("start: array")
    tree = parser.parse("""
OPEN/CLOSE some.file
    """)
    print(tree.pretty())
    assert len(tree.children) == 1
    array = tree.children[0]
    assert str(array.data) == "array"
    single_array = array.children[0]
    assert str(single_array.data) == "single_array"
    readarray = single_array.children[-1]  # optional netcdf comes first
    assert str(readarray.data) == "readarray"
    control = readarray.children[0]
    assert str(control.data) == "control"
    external = control.children[0]
    assert str(external.data) == "external"
    filename = external.children[0]
    assert str(filename.data) == "filename"
    # there's an intermediate "word",
    # TODO any way to get rid of it?
    assert str(filename.children[0].children[0]) == "some.file"


def test_parse_external_array_with_quotation_marks():
    parser = typed_parser("start: array")
    tree = parser.parse("""
OPEN/CLOSE "some.file"
    """)
    print(tree.pretty())
    assert len(tree.children) == 1
    array = tree.children[0]
    assert str(array.data) == "array"
    single_array = array.children[0]
    assert str(single_array.data) == "single_array"
    readarray = single_array.children[-1]
    assert str(readarray.data) == "readarray"
    control = readarray.children[0]
    assert str(control.data) == "control"
    external = control.children[0]
    assert str(external.data) == "external"
    filename = external.children[0]
    assert str(filename.data) == "filename"
    assert str(filename.children[0]) == '"some.file"'


def test_transform_internal_array():
    parser = typed_parser("start: array")
    transformer = TypedTransformer()
    result = transformer.transform(
        parser.parse("""
INTERNAL FACTOR 1.5 IPRN 3
1.2 3.7 9.3 4.2
2.2 9.9 1.0 3.3
4.9 7.3 7.5 8.2
8.7 6.6 4.5 5.7
    """)
    )
    assert result["control"]["type"] == "internal"
    assert result["control"]["factor"] == 1.5
    assert result["control"]["iprn"] == 3
    assert result["data"].shape == (16,)


def test_transform_constant_array():
    parser = typed_parser("start: array")
    transformer = TypedTransformer()
    result = transformer.transform(
        parser.parse("""
CONSTANT 42.5
    """)
    )
    assert result["control"]["type"] == "constant"
    assert np.array_equal(result["data"], np.array(42.5))


def test_transform_external_array():
    parser = typed_parser("start: array")
    transformer = TypedTransformer()
    result = transformer.transform(
        parser.parse("""
OPEN/CLOSE "data/heads.dat" FACTOR 1.0 (BINARY)
    """)
    )
    assert result["control"]["type"] == "external"
    assert result["data"] == Path("data/heads.dat")


def test_transform_layered_array():
    parser = typed_parser("start: array")
    transformer = TypedTransformer()
    result = transformer.transform(
        parser.parse("""
LAYERED
CONSTANT 1.0
INTERNAL FACTOR 2.0
1.2 3.7 9.3 4.2
2.2 9.9 1.0 3.3
    """)
    )
    assert isinstance(result["control"], list)
    assert result["control"][0]["type"] == "constant"
    assert result["control"][1]["type"] == "internal"
    assert result["control"][1]["factor"] == 2.0
    assert isinstance(result["data"], xr.DataArray)
    assert result["data"].shape == (2, 8)
    assert result["data"].dims == ("layer", "dim_0")
    assert np.array_equal(result["data"][0], np.ones((8,)))


def test_transform_full_component():
    dfn = Dfn(
        **{
            "name": "test_transform",
            "schema_version": Version("2"),
            "blocks": {
                "options": {
                    "r2d2": {"name": "r2d2", "type": "keyword"},
                    "b": {"name": "b", "type": "string"},
                    "c": {"name": "c", "type": "integer"},
                    "p": {"name": "p", "type": "double"},
                },
                "arrays": {
                    "x": {"name": "x", "type": "double", "shape": None},
                    "y": {"name": "y", "type": "array", "shape": None},
                    "z": {"name": "z", "type": "array", "shape": None},
                },
            },
        }
    )
    grammar = """
start: block*
block: options_block | arrays_block
options_block: "begin"i "options"i options_fields "end"i "options"i
arrays_block: "begin"i "arrays"i arrays_fields "end"i "arrays"i
options_fields: (r2d2 | b | c | p)*
arrays_fields: (x | y | z)*
r2d2: "r2d2"i // keyword
b: "b"i string
c: "c"i integer
p: "p"i double
x: "x"i array
y: "y"i array
z: "z"i array
"""
    parser = typed_parser(grammar)
    transformer = TypedTransformer(dfn=dfn)
    result = transformer.transform(
        parser.parse("""
BEGIN OPTIONS
    R2D2
    B "nice said"
    C 3
    P 0.
END OPTIONS
BEGIN ARRAYS
    X CONSTANT 1.0
    Y INTERNAL 4.0 5.0 6.0
    Z OPEN/CLOSE "data/z.dat" FACTOR 1.0 (BINARY)
END ARRAYS
""")
    )
    assert "options" in result
    assert "arrays" in result
    assert result["options"]["r2d2"] is True
    assert result["options"]["b"] == "nice said"
    assert result["options"]["c"] == 3
    assert result["options"]["p"] == 0.0
    assert result["arrays"]["x"]["control"]["type"] == "constant"
    assert np.array_equal(result["arrays"]["x"]["data"], np.array(1.0))
    assert result["arrays"]["y"]["control"]["type"] == "internal"
    assert np.array_equal(result["arrays"]["y"]["data"], np.array([4.0, 5.0, 6.0]))
    assert result["arrays"]["z"]["control"]["type"] == "external"
    assert result["arrays"]["z"]["control"]["factor"] == 1.0
    assert result["arrays"]["z"]["control"]["binary"] is True
    assert result["arrays"]["z"]["data"] == Path("data/z.dat")


# Real model tests using modflow-devtools models API


MF6_EXAMPLES_URL = (
    "https://github.com/MODFLOW-ORG/modflow6-examples/releases/download/current/mf6examples.zip"
)


@pytest.fixture(scope="session")
def mf6_examples_path(tmp_path_factory):
    """Download and cache MF6 example models for the test session."""
    tmp_dir = tmp_path_factory.mktemp("mf6_examples")
    download_and_unzip(MF6_EXAMPLES_URL, tmp_dir, verbose=False)
    return tmp_dir


@pytest.fixture
def model_workspace(mf6_examples_path, request):
    """Get a model directory from downloaded examples.

    The request.param should be in the form 'mf6/example/ex-gwf-csub-p01',
    and the model directory name is the last component.
    """
    model_name = request.param
    # Extract dir name from model path
    # e.g. "mf6/example/ex-gwf-csub-p01" -> "ex-gwf-csub-p01"
    dir_name = model_name.split("/")[-1]
    workspace = mf6_examples_path / dir_name
    if not workspace.exists():
        pytest.skip(f"Model directory '{dir_name}' not found in downloaded examples")
    return workspace


@pytest.mark.parametrize("model_workspace", ["mf6/example/ex-gwf-csub-p01"], indirect=True)
def test_parse_gwf_ic_file(model_workspace):
    """Test parsing a GWF IC (initial conditions) file from a real model."""
    # Find the IC file in the model workspace
    ic_files = list(model_workspace.rglob("*.ic"))
    assert len(ic_files) > 0, "No IC files found in model workspace"

    ic_file = ic_files[0]
    parser = get_typed_parser("gwf-ic")

    # Read and parse the file
    with open(ic_file, "r") as f:
        content = f.read()

    tree = parser.parse(content)
    assert tree is not None

    # Basic structure checks
    assert tree.data == "start"
    assert len(tree.children) > 0  # Should have at least one block


@pytest.mark.parametrize("model_workspace", ["mf6/example/ex-gwf-bcf2ss-p01a"], indirect=True)
def test_parse_gwf_wel_file(model_workspace):
    """Test parsing a GWF WEL (well) file with period data from a real model."""
    # Find the WEL file in the model workspace
    wel_files = list(model_workspace.rglob("*.wel"))

    # Skip if no WEL files (not all models have wells)
    if len(wel_files) == 0:
        pytest.skip("No WEL files found in this model")

    wel_file = wel_files[0]
    parser = get_typed_parser("gwf-wel")

    # Read and parse the file
    with open(wel_file, "r") as f:
        content = f.read()

    tree = parser.parse(content)
    assert tree is not None

    # Basic structure checks
    assert tree.data == "start"
    assert len(tree.children) > 0

    # Should have blocks
    blocks = [child for child in tree.children if child.data == "block"]
    assert len(blocks) > 0

    # Should have period blocks (nested inside block nodes)
    period_blocks = [
        block.children[0]
        for block in blocks
        if block.children and block.children[0].data == "period_block"
    ]
    assert len(period_blocks) > 0, "Should have at least one period block"


@pytest.mark.parametrize("model_workspace", ["mf6/example/ex-gwf-csub-p01"], indirect=True)
def test_transform_gwf_ic_file(model_workspace, dfn_path):
    """Test transforming a parsed GWF IC file into structured data."""

    v1_dfns = Dfn.load_all(dfn_path, schema_version="2.0.0.dev1")
    ic_dfn = v1_dfns["gwf-ic"]

    # Find the IC file
    ic_files = list(model_workspace.rglob("*.ic"))
    assert len(ic_files) > 0

    ic_file = ic_files[0]
    parser = get_typed_parser("gwf-ic")
    transformer = TypedTransformer(dfn=ic_dfn)

    # Read, parse, and transform
    with open(ic_file, "r") as f:
        content = f.read()

    tree = parser.parse(content)
    result = transformer.transform(tree)

    # Check structure
    assert isinstance(result, dict)
    assert "griddata" in result  # IC has griddata block
    assert "strt" in result["griddata"]  # Starting heads

    # Check strt array structure
    strt = result["griddata"]["strt"]
    assert "control" in strt
    assert "data" in strt
    assert strt["control"]["type"] in ["constant", "internal", "external"]

    # If internal or constant, should have data
    if strt["control"]["type"] in ["constant", "internal"]:
        assert strt["data"] is not None


@pytest.mark.parametrize("model_workspace", ["mf6/example/ex-gwf-bcf2ss-p01a"], indirect=True)
def test_transform_gwf_wel_file(model_workspace, dfn_path):
    """Test transforming a parsed GWF WEL file into structured data."""

    v1_dfns = Dfn.load_all(dfn_path, schema_version="2.0.0.dev1")
    wel_dfn = v1_dfns["gwf-wel"]

    # Find the WEL file
    wel_files = list(model_workspace.rglob("*.wel"))

    # Skip if no WEL files (not all models have wells)
    if len(wel_files) == 0:
        pytest.skip("No WEL files found in this model")

    wel_file = wel_files[0]
    parser = get_typed_parser("gwf-wel")
    transformer = TypedTransformer(dfn=wel_dfn)

    # Read, parse, and transform
    with open(wel_file, "r") as f:
        content = f.read()

    tree = parser.parse(content)
    result = transformer.transform(tree)

    # Check structure
    assert isinstance(result, dict)

    # Check dimensions block
    assert "dimensions" in result
    assert result["dimensions"]["maxbound"] == 2

    # Should have a period 2 entry (indexed period blocks are flattened to "period N" keys)
    assert "period 2" in result
    assert "stress_period_data" in result["period 2"]

    # Should have 2 rows of data (MAXBOUND = 2)
    spd = result["period 2"]["stress_period_data"]
    assert len(spd) == 2

    # Each row should have 4 values (cellid components + q value)
    assert len(spd[0]) == 4
    assert len(spd[1]) == 4

    # Check specific values from the file
    # First well: 2 3 4 -3.5e4
    assert spd[0][0] == 2  # layer
    assert spd[0][1] == 3  # row
    assert spd[0][2] == 4  # col
    assert spd[0][3] == -3.5e4  # q

    # Second well: 2 8 4 -3.5e4
    assert spd[1][0] == 2  # layer
    assert spd[1][1] == 8  # row
    assert spd[1][2] == 4  # col
    assert spd[1][3] == -3.5e4  # q


@pytest.mark.parametrize("model_workspace", ["mf6/example/ex-gwf-bcf2ss-p01a"], indirect=True)
def test_parse_gwf_oc_file(model_workspace):
    """Test parsing a GWF OC (output control) file from a real model."""
    # Find the OC file in the model workspace
    oc_files = list(model_workspace.rglob("*.oc"))
    assert len(oc_files) > 0, "No OC files found in model workspace"

    oc_file = oc_files[0]
    parser = get_typed_parser("gwf-oc")

    # Read and parse the file
    with open(oc_file, "r") as f:
        content = f.read()

    tree = parser.parse(content)
    assert tree is not None

    # Basic structure checks
    assert tree.data == "start"
    assert len(tree.children) > 0  # Should have at least one block

    # Should have blocks
    blocks = [child for child in tree.children if child.data == "block"]
    assert len(blocks) > 0


@pytest.mark.parametrize("model_workspace", ["mf6/example/ex-gwf-bcf2ss-p01a"], indirect=True)
def test_transform_gwf_oc_file(model_workspace, dfn_path):
    """Test transforming a parsed GWF OC file into structured data."""

    v1_dfns = Dfn.load_all(dfn_path, schema_version="2.0.0.dev1")
    oc_dfn = v1_dfns["gwf-oc"]

    # Find the OC file
    oc_files = list(model_workspace.rglob("*.oc"))
    assert len(oc_files) > 0

    oc_file = oc_files[0]
    parser = get_typed_parser("gwf-oc")
    transformer = TypedTransformer(dfn=oc_dfn)

    # Read, parse, and transform
    with open(oc_file, "r") as f:
        content = f.read()

    tree = parser.parse(content)
    result = transformer.transform(tree)

    # Check structure
    assert isinstance(result, dict)

    # Check options block
    assert "options" in result
    options = result["options"]

    # Should have budget and head fileout records
    assert "budget_filerecord" in options
    assert options["budget_filerecord"]["budgetfile"] == "ex-gwf-bcf2ss.cbc"

    assert "head_filerecord" in options
    assert options["head_filerecord"]["headfile"] == "ex-gwf-bcf2ss.hds"

    # Check period 1 block
    assert "period 1" in result
    period_data = result["period 1"]

    # Should have saverecord list with HEAD and BUDGET saves
    assert "saverecord" in period_data
    save_records = period_data["saverecord"]
    assert len(save_records) == 2

    # Check that HEAD and BUDGET are both saved with ALL frequency
    rtypes = [rec["rtype"] for rec in save_records]
    assert "HEAD" in rtypes
    assert "BUDGET" in rtypes

    # Check that all records use ALL frequency
    for rec in save_records:
        assert "ocsetting" in rec
        assert rec["ocsetting"] == "all"


@pytest.mark.parametrize("model_workspace", ["mf6/example/ex-gwf-csub-p01"], indirect=True)
def test_transform_gwf_dis_file(model_workspace, dfn_path):
    """Test transforming a parsed GWF DIS file into structured data."""

    # Load the DFN for DIS and convert to V2
    v1_dfns = Dfn.load_all(dfn_path, schema_version="2.0.0.dev1")
    dis_dfn = v1_dfns["gwf-dis"]

    # Find the DIS file
    dis_files = list(model_workspace.rglob("*.dis"))
    assert len(dis_files) > 0

    dis_file = dis_files[0]
    parser = get_typed_parser("gwf-dis")
    transformer = TypedTransformer(dfn=dis_dfn)

    # Read, parse, and transform
    with open(dis_file, "r") as f:
        content = f.read()

    tree = parser.parse(content)
    result = transformer.transform(tree)

    # Check structure
    assert isinstance(result, dict)

    # Check dimensions block
    assert "dimensions" in result
    assert "nlay" in result["dimensions"]
    assert "nrow" in result["dimensions"]
    assert "ncol" in result["dimensions"]
    assert result["dimensions"]["nlay"] > 0
    assert result["dimensions"]["nrow"] > 0
    assert result["dimensions"]["ncol"] > 0

    # Check griddata block
    assert "griddata" in result
    griddata = result["griddata"]
    assert "delr" in griddata
    assert "delc" in griddata
    assert "top" in griddata
    assert "botm" in griddata

    # Each array should have control and data
    assert "control" in griddata["delr"]
    assert "data" in griddata["delr"]


@pytest.mark.parametrize("model_workspace", ["mf6/example/ex-gwf-csub-p01"], indirect=True)
def test_transform_gwf_npf_file(model_workspace, dfn_path):
    """Test transforming a parsed GWF NPF file into structured data."""

    # Load the DFN for NPF and convert to V2
    v1_dfns = Dfn.load_all(dfn_path, schema_version="2.0.0.dev1")
    npf_dfn = v1_dfns["gwf-npf"]

    # Find the NPF file
    npf_files = list(model_workspace.rglob("*.npf"))
    assert len(npf_files) > 0

    npf_file = npf_files[0]
    parser = get_typed_parser("gwf-npf")
    transformer = TypedTransformer(dfn=npf_dfn)

    # Read, parse, and transform
    with open(npf_file, "r") as f:
        content = f.read()

    tree = parser.parse(content)
    result = transformer.transform(tree)

    # Check structure
    assert isinstance(result, dict)

    # Check options block
    assert "options" in result
    options = result["options"]

    # Should have save_specific_discharge option
    assert "save_specific_discharge" in options
    assert options["save_specific_discharge"] is True

    # Check griddata block
    assert "griddata" in result
    griddata = result["griddata"]

    # NPF should have at least icelltype and k
    assert "icelltype" in griddata
    assert "k" in griddata

    # Each array should have control and data
    assert "control" in griddata["icelltype"]
    assert "data" in griddata["icelltype"]
    assert "control" in griddata["k"]
    assert "data" in griddata["k"]


@pytest.mark.parametrize("model_workspace", ["mf6/example/ex-gwf-csub-p01"], indirect=True)
def test_transform_gwf_sto_file(model_workspace, dfn_path):
    """Test transforming a parsed GWF STO file into structured data."""

    # Load the DFN for STO and convert to V2
    v1_dfns = Dfn.load_all(dfn_path, schema_version="2.0.0.dev1")
    sto_dfn = v1_dfns["gwf-sto"]

    # Find the STO file
    sto_files = list(model_workspace.rglob("*.sto"))

    # Skip if no STO files (not all models have storage)
    if len(sto_files) == 0:
        pytest.skip("No STO files found in this model")

    sto_file = sto_files[0]
    parser = get_typed_parser("gwf-sto")
    transformer = TypedTransformer(dfn=sto_dfn)

    # Read, parse, and transform
    with open(sto_file, "r") as f:
        content = f.read()

    tree = parser.parse(content)
    result = transformer.transform(tree)

    # Check structure
    assert isinstance(result, dict)

    # Check griddata block
    assert "griddata" in result
    griddata = result["griddata"]

    # STO should have iconvert
    assert "iconvert" in griddata
    assert "control" in griddata["iconvert"]
    assert "data" in griddata["iconvert"]
