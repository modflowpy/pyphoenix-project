"""Generate Lark grammars from DFN files."""

import argparse
import sys
from os import PathLike
from pathlib import Path

from modflow_devtools.dfns.schema import Component

from flopy4.mf6.codec.reader.grammar import make_grammars

_GRAMMAR_MODULE = Path(__file__).parent / "grammar"
_GRAMMAR_GEN_DIR = _GRAMMAR_MODULE / "generated"

_DFN_SCHEMA_VERSION = "2.0.0.dev3"


def make(dfns: dict[str, Component], outdir: str | PathLike):
    """Generate lark grammars from a pre-loaded {name: Component} dict.

    Parameters
    ----------
    dfns :
        Pre-loaded DFN dict, e.g. from a registry's ``.spec()`` call.
    """
    outdir = Path(outdir).expanduser().absolute()
    outdir.mkdir(exist_ok=True, parents=True)
    make_grammars(dfns, outdir)


def main() -> None:
    """Command-line entry point."""
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

    from modflow_devtools.dfns import LocalDfnRegistry

    registry = LocalDfnRegistry(path=Path(args.dfndir))
    dfns = registry.spec(schema_version=_DFN_SCHEMA_VERSION).components

    try:
        make(dfns, args.outdir)
    except (EOFError, KeyboardInterrupt):
        sys.exit(f"Cancelled '{sys.argv[0]}'")


if __name__ == "__main__":
    main()
