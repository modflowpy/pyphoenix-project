"""Convert (TOML/v2) DFNs to Lark grammars."""

import argparse
from os import PathLike
from pathlib import Path

from modflow_devtools.dfn import load_flat, map

from flopy4.mf6.codec.reader.grammar import make_grammars

_GRAMMAR_MODULE = Path(__file__).parent / "grammar"
_GRAMMAR_GEN_DIR = _GRAMMAR_MODULE / "generated"


def make(dfndir: str | PathLike, outdir: str | PathLike):
    """Generate lark grammars from DFNs."""
    dfndir = Path(dfndir).expanduser().absolute()
    outdir = Path(outdir).expanduser().absolute()
    outdir.mkdir(exist_ok=True, parents=True)
    dfns_v1 = load_flat(dfndir)
    dfns_v2 = {name: map(dfn, schema_version=2) for name, dfn in dfns_v1.items()}
    make_grammars(dfns_v2, outdir)


def main():
    parser = argparse.ArgumentParser(description="Generate lark grammars from definition files.")
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
    make(args.dfndir, args.outdir)


if __name__ == "__main__":
    main()
