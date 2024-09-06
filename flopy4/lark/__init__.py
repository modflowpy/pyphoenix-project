from lark import Lark

MF6_GRAMMAR = r"""
// component
component: _NL* (block _NL+)* _NL*

// blocks
block: _paramsblock | _listblock
_paramsblock: _BEGIN paramsblockname _NL params _END paramsblockname
_listblock: _BEGIN listblockname _NL list _END listblockname
paramsblockname: PARAMSBLOCKNAME
listblockname: LISTBLOCKNAME [_blockindex]
_blockindex: INT
_BEGIN: "begin"i
_END: "end"i

// parameters (higher priority than lists
// since list of records will match also)
params.1: (param _NL)*
param: key | _pair
_pair: key value
key: PARAMNAME
?value: array
      | list
      | path
      | string
      | int
      | float

// string
word: WORD
?string: word+

// numbers
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

// list adapted from https://github.com/lark-parser/lark/blob/master/examples/composition/csv.lark
list.-1: record*
// negative priority for records bc
// the pattern is so indiscriminate.
record.-1: _anything+ _NL
_anything: int | float | word
NON_SEPARATOR_STRING: /[a-zA-z.;\\\/]+/

// newline
_NL: /(\r?\n[\t ]*)+/

// TODO:
// a parameter key file can be generated
// with the rest of the plugin interface
// rather than known keys hardcoded here
// (and likewise for block names)
PARAMNAME: ("K"|"I"|"D"|"S"|"F"|"A")
PARAMSBLOCKNAME: ("OPTIONS"|"PACKAGEDATA")
LISTBLOCKNAME: "PERIOD"

%import common.SH_COMMENT -> COMMENT
%import common.SIGNED_NUMBER -> NUMBER
%import common.SIGNED_INT -> INT
%import common.SIGNED_FLOAT -> FLOAT
%import common.WORD
%import common.WS_INLINE

%ignore COMMENT
%ignore WS_INLINE
"""

MF6_PARSER = Lark(MF6_GRAMMAR, start="component")
