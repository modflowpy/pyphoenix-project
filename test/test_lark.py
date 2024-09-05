from pprint import pprint

import pytest
from lark import Transformer

from flopy4.lark import MF6_PARSER

TEST_PKG = """
BEGIN OPTIONS
  K
  I 1
  D 1.0
  S hello world
  F FILEIN some/path
END OPTIONS

BEGIN PACKAGEDATA 1
  A INTERNAL 1.0 2.0 3.0
END PACKAGEDATA
"""


def test_parse_mf6():
    tree = MF6_PARSER.parse(TEST_PKG)
    # this is working, check it with:
    # pytest test/test_lark.py::test_parse_mf6 -s
    print(tree.pretty())


class MF6Transformer(Transformer):
    # TODO
    pass


MF6_TRANSFORMER = MF6Transformer()


@pytest.mark.xfail
def test_transform_mf6():
    tree = MF6_PARSER.parse(TEST_PKG)
    data = MF6_TRANSFORMER.transform(tree)
    pprint(data)
