from pathlib import Path

from lark import Lark

MF6_GRAMMAR_PATH = Path(__file__).parent / "mf6.lark"
MF6_PARSER = Lark.open(MF6_GRAMMAR_PATH, rel_to=__file__, start="start")
