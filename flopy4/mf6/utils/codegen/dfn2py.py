"""Generate an MF6 module from DFN files."""

import argparse
import sys
from os import PathLike
from pathlib import Path

from flopy4.mf6.utils.codegen.make import make_modules

_PROJ_ROOT = Path(__file__).parents[4].expanduser().resolve()
_MF6_ROOT = _PROJ_ROOT / "flopy4" / "mf6"

# DFN names that require special handling beyond simple package generation.
# These are skipped until their generation tier is implemented.
#
# nam files: model/simulation name files need special model-level handling.
# dis/disv: require DisBase + grid conversion methods (dis tier).
# tdis/ims: top-level hand-written files, not yet templated.
# *g / *a variants: gridded/array package variants, deferred.
#
# TODO (subpackage tier): detect `# flopy subpackage` DFN annotations and emit
# a typed child attrs field (e.g. ncf: Optional[Ncf]) alongside the existing path
# field; DisBase.write() already establishes the write pattern for NCF.
# utl-ts also needs period values referencing timeseries by name written as strings.
_SKIP = {
    # discretization tier (require DisBase + grid methods)
    "gwf-dis",
    "gwf-disv",
    "gwt-dis",
    "gwe-dis",
    "prt-dis",
    # time discretization (hand-written tdis.py)
    "sim-tdis",
    # hand-written: wkt field type override + Ncf.from_grid() factory.
    # TODO: move factory to NcfBase (utl/ncf_base.py) so codegen can own utl/ncf.py,
    # matching the DisBase pattern used for discretization packages.
    "utl-ncf",
}


def make(
    dfns: dict,
    outdir: str | PathLike = _MF6_ROOT,
    developmode: bool = False,
    makedirs: bool = False,
    existing_only: bool = False,
    verbose: bool = False,
):
    """Generate an MF6 module from DFNs.

    Parameters
    ----------
    dfns :
        Pre-loaded DFN dict, e.g. from a registry's `spec()` call.
    """
    outdir = Path(outdir).expanduser().resolve()
    outdir.mkdir(exist_ok=True, parents=True)
    components = make_modules(
        dfns=dfns,
        outdir=outdir,
        developmode=developmode,
        skip=_SKIP,
        makedirs=makedirs,
        existing_only=existing_only,
        verbose=verbose,
    )
    print(f"Generated {len(components)} component modules")


def cli_main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Generate MF6 Python classes from DFN specification files.",
    )
    parser.add_argument(
        "--dfndir",
        "-d",
        type=str,
        help="Directory containing DFN files.",
    )
    parser.add_argument(
        "--outdir",
        default=str(_MF6_ROOT),
        help="Root output directory (default: flopy4/mf6/ in the project).",
    )
    parser.add_argument(
        "--developmode",
        action="store_true",
        help="Include developmode fields.",
    )
    parser.add_argument(
        "--makedirs",
        action="store_true",
        help="Create missing output subdirectories (useful for preview paths).",
    )
    parser.add_argument(
        "--existing-only",
        action="store_true",
        help="Only regenerate files that already exist on disk.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    from modflow_devtools.dfns import LocalDfnRegistry

    registry = LocalDfnRegistry(path=Path(args.dfndir))
    dfns = registry.spec(schema_version="2.0.0.dev3").components

    try:
        make(
            dfns=dfns,
            outdir=args.outdir,
            developmode=args.developmode,
            makedirs=args.makedirs,
            existing_only=args.existing_only,
            verbose=args.verbose,
        )
    except (EOFError, KeyboardInterrupt):
        sys.exit(f"Cancelled '{sys.argv[0]}'")


if __name__ == "__main__":
    cli_main()
