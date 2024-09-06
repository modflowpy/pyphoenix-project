from os import linesep
from pathlib import Path

import numpy as np
from lark import Transformer

from flopy4.lark import MF6_PARSER

TEST_COMPONENT = """
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


def test_parse():
    tree = MF6_PARSER.parse(TEST_COMPONENT)
    # view the parse tree with e.g.
    #   pytest test/test_lark.py::test_parse -s
    print(linesep + tree.pretty())


class MF6Transformer(Transformer):
    def key(self, k):
        (k,) = k
        return str(k).lower()

    def word(self, w):
        (w,) = w
        return str(w)

    def path(self, p):
        _, p = p
        return Path(p)

    def string(self, s):
        return " ".join(s)

    def int(self, i):
        (i,) = i
        return int(i)

    def float(self, f):
        (f,) = f
        return float(f)

    def array(self, a):
        (a,) = a
        return a

    def constantarray(self, a):
        # TODO factor out `ConstantArray`
        # array-like class from `MFArray`
        # with deferred shape and use it
        pass

    def internalarray(self, a):
        factor = a[0]
        array = np.array(a[2:])
        if factor is not None:
            array *= factor
        return array

    def externalarray(self, a):
        # TODO
        pass

    record = tuple
    list = list

    def param(self, p):
        k = p[0]
        v = True if len(p) == 1 else p[1]
        return k, v

    params = dict

    def block(self, b):
        return tuple(b[:2])

    def paramsblockname(self, bn):
        return str(bn[0]).lower()

    def listblockname(self, bn):
        name = str(bn[0])
        if len(bn) == 2:
            index = int(bn[1])
            name = f"{name} {index}"
        return name.lower()

    component = dict


MF6_TRANSFORMER = MF6Transformer()


def test_transform():
    tree = MF6_PARSER.parse(TEST_COMPONENT)
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
