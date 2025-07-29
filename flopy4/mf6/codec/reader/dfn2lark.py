"""Convert (TOML/v2) DFNs to Lark grammars."""

import argparse
from os import PathLike
from pathlib import Path

from modflow_devtools.dfn import Dfn

from flopy4.mf6.codec.reader.grammar import make_all_grammars

_GRAMMAR_MODULE = Path(__file__).parent / "grammar"
_GRAMMAR_GEN_DIR = _GRAMMAR_MODULE / "generated"


def generate(dfndir: PathLike, outdir: PathLike):
    """Generate lark grammars from DFNs."""
    dfndir = Path(dfndir).expanduser().absolute()
    outdir = Path(outdir).expanduser().absolute()
    outdir.mkdir(exist_ok=True, parents=True)
    dfns = Dfn.load_all(dfndir, version=2)
    make_all_grammars(dfns, outdir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate lark grammars from DFNs.")
    parser.add_argument(
        "--dfndir",
        "-d",
        type=str,
        help="Directory containing DFN files.",
    )
    parser.add_argument(
        "--outdir",
        "-o",
        help="Output directory.",
        default=_GRAMMAR_GEN_DIR,
    )
    args = parser.parse_args()
    generate(args.dfndir, args.outdir)
