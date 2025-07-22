from pathlib import Path

import numpy as np
import xarray as xr

from flopy4.mf6.codec.reader.parser import make_array_parser
from flopy4.mf6.codec.reader.transformer import ArrayTransformer


def test_parse_internal_array():
    parser = make_array_parser()
    tree = parser.parse("""
INTERNAL FACTOR 1.0 IPRN 3
1.2 3.7 9.3 4.2 2.2 9.9 1.0 
3.3 4.9 7.3 7.5 8.2 8.7 6.6 
4.5 5.7 2.2 1.1 1.7 6.7 6.9 
7.4 3.5 7.8 8.5 7.4 6.8 8.8
    """)
    print(tree.pretty())


def test_parse_layered_array():
    parser = make_array_parser()
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
    parser = make_array_parser()
    tree = parser.parse("""
CONSTANT 1.0
    """)
    print(tree.pretty())


def test_parse_external_array_no_quotation_marks():
    parser = make_array_parser()
    tree = parser.parse("""
OPEN/CLOSE some.file
    """)
    print(tree.pretty())


def test_parse_external_array_with_quotation_marks():
    parser = make_array_parser()
    tree = parser.parse("""
OPEN/CLOSE "some.file"
    """)
    print(tree.pretty())


def test_transform_internal_array():
    parser = make_array_parser()
    transformer = ArrayTransformer()
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
    parser = make_array_parser()
    transformer = ArrayTransformer()
    result = transformer.transform(
        parser.parse("""
CONSTANT 42.5
    """)
    )
    assert result["control"]["type"] == "constant"
    assert result["data"] == 42.5


def test_transform_external_array():
    parser = make_array_parser()
    transformer = ArrayTransformer()
    result = transformer.transform(
        parser.parse("""
OPEN/CLOSE "data/heads.dat" FACTOR 1.0 (BINARY)
    """)
    )
    assert result["control"]["type"] == "external"
    assert result["data"] == Path("data/heads.dat")


def test_transform_layered_array():
    parser = make_array_parser()
    transformer = ArrayTransformer()
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
