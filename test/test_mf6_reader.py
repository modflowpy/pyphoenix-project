"""Test the MF6 input file reader as implemented with lark."""

import os
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
from lark import Lark
from modflow_devtools.dfn import Dfn
from modflow_devtools.models import get_models
from packaging.version import Version

from flopy4.mf6.codec.reader.parser import get_typed_parser
from flopy4.mf6.codec.reader.transformer import TypedTransformer

PROJ_ROOT_PATH = Path(__file__).parents[1]
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


def test_parse_constant_array():
    parser = typed_parser("start: array")
    tree = parser.parse("""
CONSTANT 1.0
    """)
    print(tree.pretty())


def test_parse_external_array_no_quotation_marks():
    parser = typed_parser("start: array")
    tree = parser.parse("""
OPEN/CLOSE some.file
    """)
    print(tree.pretty())


def test_parse_external_array_with_quotation_marks():
    parser = typed_parser("start: array")
    tree = parser.parse("""
OPEN/CLOSE "some.file"
    """)
    print(tree.pretty())


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
    dfn = Dfn.from_dict(
        {
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
options_block: "begin"i "options"i options_vars "end"i "options"i
arrays_block: "begin"i "arrays"i arrays_vars "end"i "arrays"i
options_vars: (r2d2 | b | c | p)*
arrays_vars: (x | y | z)*
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


@pytest.fixture(scope="module")
def example_models():
    """Get MF6 example models from devtools."""
    models = get_models()
    # Filter to mf6 examples only
    return {name: info for name, info in models.items() if name.startswith("mf6/example/")}


@pytest.fixture
def model_workspace(tmp_path, request):
    """Copy a model to a temporary workspace."""
    from modflow_devtools.models import copy_to

    model_name = request.param
    workspace = copy_to(tmp_path, model_name, verbose=False)
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

    # Should have period blocks
    period_blocks = [child for child in tree.children if child.data == "period_block"]
    assert len(period_blocks) > 0, "Should have at least one period block"


@pytest.mark.parametrize("model_workspace", ["mf6/example/ex-gwf-csub-p01"], indirect=True)
def test_transform_gwf_ic_file(model_workspace):
    """Test transforming a parsed GWF IC file into structured data."""
    from modflow_devtools.dfn import load_dfns

    # Load the DFN for IC
    dfns = load_dfns("../modflow-devtools/autotest/temp/dfn/toml")
    ic_dfn = dfns["gwf-ic"]

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
