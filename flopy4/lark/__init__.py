from lark import Lark

MF6_GRAMMAR = r"""
?start: _NL* _item*
_item: (block | COMMENT) _NL+

// block
block: _begin _NL params _end 
_begin: _BEGIN name [index]
_end: _END name
name: WORD
index: INT
_BEGIN: "begin"i
_END: "end"i

// parameter
params: (param _NL)*
param: _key [_value]
_key: KEYS
_value: NUMBER | path | string | array | list

// string
string: WORD+

// file path
path: INOUT PATH
PATH: [_PATHSEP] (NON_SEPARATOR_STRING [_PATHSEP]) [NON_SEPARATOR_STRING]
_PATHSEP: "/"
INOUT: "filein"i|"fileout"i

// array
array: constantarray | internalarray | externalarray
constantarray: "CONSTANT" NUMBER
internalarray: "INTERNAL" [factor] [iprn] (NUMBER* [_NL])*
externalarray: "OPEN/CLOSE" WORD [factor] ["binary"] [iprn]
factor: "FACTOR" NUMBER
iprn: "IPRN" INT

// list (adapted from https://github.com/lark-parser/lark/blob/master/examples/composition/csv.lark)
list: header _NL row*
header: "#" " "? (WORD _SEPARATOR?)+
row: (_anything _SEPARATOR?)+ _NL
_anything: INT | WORD | NON_SEPARATOR_STRING | FLOAT | SIGNED_FLOAT
NON_SEPARATOR_STRING: /[a-zA-z.;\\\/]+/
_SEPARATOR: /[  ]+/
          | "\t"
          | ","

// newline
_NL: /(\r?\n[\t ]*)+/

// parameter keys file can be generated
// with the rest of the plugin interface
// and maybe placed in a separate file
KEYS: "K"|"I"|"D"|"S"|"F"|"A"

%import common.SH_COMMENT -> COMMENT
%import common.SIGNED_NUMBER -> NUMBER
%import common.SIGNED_FLOAT
%import common.INT
%import common.FLOAT
%import common.WORD
%import common.WS_INLINE

%ignore WS_INLINE
"""

MF6_PARSER = Lark(MF6_GRAMMAR, start="start")
