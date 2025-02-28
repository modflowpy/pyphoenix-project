from lark import Lark

from flopy4.mf6.gwf.oc import Oc
from flopy4.mf6.io import make_parser


def test_make_parser():
    parser = make_parser(Oc)
    assert isinstance(parser, Lark)
