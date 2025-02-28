from os import linesep
from pathlib import Path

import numpy as np
from lark import Lark, Transformer
from xattree import has_xats

__all__ = ["make_parser", "MF6Transformer"]


_GRAMMAR = r"""
// component
component: _NL* (block _NL+)+ _NL*

// block
block: _dictblock | _listblock
_dictblock: _BEGIN dictblock _NL dict _END dictblock
_listblock: _BEGIN listblock _NL list _END listblock
dictblock: DICTBLOCK
listblock: LISTBLOCK [_blockindex]
_blockindex: INT
_BEGIN: "begin"i
_END: "end"i

// dict
dict.1: (param _NL)*

// list adapted from https://github.com/lark-parser/lark/blob/master/examples/composition/csv.lark
// negative priority for records because the pattern is so indiscriminate
list.-1: record*
record.-1: _record+ _NL
_record: scalar

// parameter
param: key | _pair
_pair: key value
key: PARAM
?value: array
      | list
      | path
      | string
      | scalar
?scalar: int
       | float
       | word

// string
word: WORD
?string: word+
NON_SEPARATOR_STRING: /[a-zA-z.;\\\/]+/

// number
int: INT
float: FLOAT

// file path
path: INOUT PATH
PATH: [_PATHSEP] (NON_SEPARATOR_STRING [_PATHSEP]) [NON_SEPARATOR_STRING]
_PATHSEP: "/"
INOUT: "filein"i|"fileout"i

// array
array: constantarray | internalarray | externalarray
constantarray: "CONSTANT" float
internalarray: "INTERNAL" [factor] [iprn] (float* [_NL])*
externalarray: "OPEN/CLOSE" PATH [factor] ["binary"] [iprn]
factor: "FACTOR" NUMBER
iprn: "IPRN" INT

// newline
_NL: /(\r?\n[\t ]*)+/

%import common.SH_COMMENT -> COMMENT
%import common.SIGNED_NUMBER -> NUMBER
%import common.SIGNED_INT -> INT
%import common.SIGNED_FLOAT -> FLOAT
%import common.WORD
%import common.WS_INLINE

%ignore COMMENT
%ignore WS_INLINE
"""
"""
EBNF description for the MODFLOW 6 input language.
"""


def make_parser(cls: type, **kwargs) -> Lark:
    """
    Create a parser for the MODFLOW 6 input language with the given
    parameter and block specification.

    Notes
    -----
    Blocks with just parameters must be handled separately because
    the pattern for list elements (records) casts a wider net than
    the pattern for parameters, which can cause a dictionary block
    of named parameters to parse as a block with a list of records.
    """
    if not has_xats(cls):
        raise ValueError(f"Class '{cls.__name__}' is not a `xattree`.")
    spec = cls.__xattree__["spec"].flat
    params = "|".join(['"' + n + '"i' for n in spec.keys()])
    blocks = set([xat.metadata.get("block", None) for xat in spec.values()])
    blocks.discard(None)
    # temp hack, TODO detect list blocks as blocks with a single
    # parameter with list or array type
    dict_blocks = [b for b in blocks if b not in ["perioddata"]]
    list_blocks = [b for b in blocks if b in ["perioddata"]]
    dict_blocks = "|".join(['"' + n + '"i' for n in dict_blocks])
    list_blocks = "|".join(['"' + n + '"i' for n in list_blocks])
    grammar = linesep.join(
        [
            _GRAMMAR,
            f"PARAM: ({params})",
            f"DICTBLOCK: ({dict_blocks})",
            f"LISTBLOCK: ({list_blocks})",
        ]
    )
    return Lark(grammar, start="component", **kwargs)


def _parse_word(_, w):
    (w,) = w
    return str(w)


def _parse_string(_, s):
    return " ".join(s)


def _parse_int(_, i):
    (i,) = i
    return int(i)


def _parse_float(_, f):
    (f,) = f
    return float(f)


def _parse_array(_, a):
    (a,) = a
    return np.array(a)


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
        # with deferred shape and use it?
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

    word = _parse_word
    string = _parse_string
    int = _parse_int
    float = _parse_float
    array = _parse_array
    record = tuple
    list = list
    dict = dict
    params = dict
    component = dict
