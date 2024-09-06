from pathlib import Path

import numpy as np
from lark import Transformer


class MF6Transformer(Transformer):
    """
    Transforms a parse tree for the MODFLOW 6 input language
    into a nested dictionary AST suitable for structuring to
    a strongly-typed input data model.

    Notes
    -----
    Each function represents a node in the tree. Its argument
    is a list of its children. Nodes are processed bottom-up,
    so non-leaf functions can assume they will get a list of
    primitives which are already in the right representation.

    See https://lark-parser.readthedocs.io/en/stable/visitors.html#transformer
    for more info.
    """

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

    def paramblock(self, bn):
        return str(bn[0]).lower()

    def listblock(self, bn):
        name = str(bn[0])
        if len(bn) == 2:
            index = int(bn[1])
            name = f"{name} {index}"
        return name.lower()

    component = dict
