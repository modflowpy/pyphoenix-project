from pathlib import Path

import numpy as np
from lark import Transformer

from flopy4.io.lark import (
    parse_array,
    parse_float,
    parse_int,
    parse_string,
    parse_word,
)


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

    def path(self, p):
        _, p = p
        return Path(p)

    def param(self, p):
        k = p[0]
        v = True if len(p) == 1 else p[1]
        return k, v

    def block(self, b):
        return tuple(b[:2])

    def dictblock(self, b):
        return str(b[0]).lower()

    def listblock(self, b):
        name = str(b[0])
        if len(b) == 2:
            index = int(b[1])
            name = f"{name} {index}"
        return name.lower()

    word = parse_word
    string = parse_string
    int = parse_int
    float = parse_float
    array = parse_array
    record = tuple
    list = list
    dict = dict
    params = dict
    component = dict
