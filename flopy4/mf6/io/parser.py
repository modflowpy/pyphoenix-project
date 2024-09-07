from os import linesep
from typing import Iterable

from lark import Lark

MF6_GRAMMAR = r"""
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


def make_parser(
    params: Iterable[str],
    dict_blocks: Iterable[str],
    list_blocks: Iterable[str],
):
    """
    Create a parser for the MODFLOW 6 input language with the given
    parameter and block specification.

    Notes
    -----
    We specify blocks containing parameters separately from blocks
    that contain a list. These must be handled separately because
    the pattern for list elements (records) casts a wider net than
    the pattern for parameters, which can cause a dictionary block
    of named parameters to parse as a block with a list of records.

    """
    params = "|".join(['"' + n + '"i' for n in params])
    dict_blocks = "|".join(['"' + n + '"i' for n in dict_blocks])
    list_blocks = "|".join(['"' + n + '"i' for n in list_blocks])
    grammar = linesep.join(
        [
            MF6_GRAMMAR,
            f"PARAM: ({params})",
            f"DICTBLOCK: ({dict_blocks})",
            f"LISTBLOCK: ({list_blocks})",
        ]
    )
    return Lark(grammar, start="component")
