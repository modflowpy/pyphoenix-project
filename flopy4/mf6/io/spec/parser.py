from os import linesep

from lark import Lark

ATTRIBUTES = [
    "block",
    "name",
    "type",
    "reader",
    "optional",
    "true",
    "mf6internal",
    "longname",
    "description",
    "layered",
    "shape",
    "valid",
    "tagged",
    "in_record",
    "preserve_case",
    "default_value",
    "numeric_index",
    "deprecated",
]

DFN_GRAMMAR = r"""
// dfn
dfn: _NL* (block _NL*)+ _NL*

// block
block: _header parameter*
_header: _hash _dashes _headtext _dashes _NL+
_headtext: component subcompnt blockname
component: _word
subcompnt: _word
blockname: _word

// parameter
parameter.+1: _paramhead _NL (attribute _NL)*
_paramhead: paramblock _NL paramname
paramblock: "block" _word
paramname: "name" _word

// attribute
attribute.-1: key value
key: ATTRIBUTE
value: string

// string
_word: /[a-zA-z0-9.;\(\)\-\,\\\/]+/
string: _word+

// newline
_NL: /(\r?\n[\t ]*)+/

// comment format
_hash: /\#/
_dashes: /[\-]+/

%import common.SH_COMMENT -> COMMENT
%import common.WORD
%import common.WS_INLINE

%ignore WS_INLINE
"""
"""
EBNF description for the MODFLOW 6 definition language.
"""


def make_parser():
    """
    Create a parser for the MODFLOW 6 definition language.
    """

    attributes = "|".join(['"' + n + '"i' for n in ATTRIBUTES])
    grammar = linesep.join([DFN_GRAMMAR, f"ATTRIBUTE: ({attributes})"])
    return Lark(grammar, start="dfn")
