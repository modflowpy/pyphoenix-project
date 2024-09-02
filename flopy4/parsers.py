from pathlib import Path

from lark import Lark

DFN_GRAMMAR_FILE = Path(__file__).parent / "dfn.lark"
MF6_GRAMMAR_FILE = Path(__file__).parent / "mf6.lark"

DFN_PARSER = Lark(open(DFN_GRAMMAR_FILE).read(), start="value")
MF6_PARSER = Lark(open(MF6_GRAMMAR_FILE).read(), start="value")
