"""
Orchestrate MF6 Python class generation from DFN specification files.

Usage (CLI)::

    pixi run python -m flopy4.mf6.utils.codegen.generate_classes --ref 6.6.0
    pixi run python -m flopy4.mf6.utils.codegen.generate_classes --dfnpath /path/to/dfns
"""

import argparse
import logging
import shutil
import sys
import tempfile
from pathlib import Path

from modflow_devtools.dfn import get_dfns
from modflow_devtools.dfns.dfn2toml import convert as dfn2toml

from .make import make_all

logger = logging.getLogger(__name__)

_PROJ_ROOT = Path(__file__).parents[4].expanduser().resolve()
_MF6_ROOT = _PROJ_ROOT / "flopy4" / "mf6"
_MF6_REPO_OWNER = "MODFLOW-ORG"
_MF6_REPO_NAME = "modflow6"

# DFN names that require special handling beyond simple package generation.
# These are skipped until their generation tier is implemented.
#
# nam files: model/simulation name files need special model-level handling.
# dis/disv: require DisBase + grid conversion methods (dis tier).
# tdis/ims: top-level hand-written files, not yet templated.
# *g / *a variants: gridded/array package variants, deferred.
_SKIP = {
    # discretization tier (require DisBase + grid methods)
    "gwf-dis",
    "gwf-disv",
    "gwt-dis",
    "gwe-dis",
    "prt-dis",
    # time discretization (hand-written tdis.py)
    "sim-tdis",
}


def generate_classes(
    owner: str = _MF6_REPO_OWNER,
    repo: str = _MF6_REPO_NAME,
    ref: str | None = None,
    dfnpath: str | None = None,
    outdir: str | Path = _MF6_ROOT,
    developmode: bool = False,
    fmt: bool = True,
    makedirs: bool = False,
    existing_only: bool = False,
) -> None:
    """Generate Python classes for MODFLOW 6 packages.

    Fetches (or reads) v1 DFN files, converts them to v2 TOML, then
    generates a Python source file for each component into ``outdir``.

    Parameters
    ----------
    owner :
        GitHub organisation that owns the MODFLOW 6 repository.
    repo :
        Repository name.
    ref :
        Branch name, tag, or commit hash to fetch DFNs from.
        Required when ``dfnpath`` is None.
    dfnpath :
        Path to a local directory of v1 ``.dfn`` files. Takes precedence
        over remote fetching when supplied.
    outdir :
        Root output directory.  Defaults to ``flopy4/mf6/`` inside the
        project so generated files land alongside hand-written ones.
    developmode :
        Include fields marked ``developmode`` in the DFN. Default False.
    fmt :
        Run ``ruff format`` / ``ruff check --fix`` on each generated file.
    """
    if dfnpath is None and ref is None:
        raise ValueError("Provide either 'ref' (remote) or 'dfnpath' (local).")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        v1dir = tmpdir / "v1"
        v2dir = tmpdir / "v2"
        v1dir.mkdir()
        v2dir.mkdir()

        if dfnpath is not None:
            src = Path(dfnpath).expanduser().resolve()
            if not src.is_dir():
                raise FileNotFoundError(f"dfnpath '{src}' is not a directory.")
            shutil.copytree(src, v1dir, dirs_exist_ok=True)
            logger.info(f"Using local DFNs from {src}")
        else:
            logger.info(f"Fetching DFNs from {owner}/{repo}@{ref}")
            get_dfns(
                owner=owner,
                repo=repo,
                ref=ref,
                outdir=v1dir,
                verbose=logger.isEnabledFor(logging.INFO),
            )

        logger.info("Converting v1 DFNs to v2 TOML")
        dfn2toml(v1dir, v2dir)

        outdir = Path(outdir).expanduser().resolve()
        generated = make_all(
            dfndir=v2dir,
            outdir=outdir,
            developmode=developmode,
            fmt=fmt,
            skip=_SKIP,
            makedirs=makedirs,
            existing_only=existing_only,
            v1dfndir=v1dir,
        )

    logger.info(f"Generated {len(generated)} files.")


def cli_main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Generate MF6 Python classes from DFN specification files.",
    )
    parser.add_argument("--owner", default=_MF6_REPO_OWNER)
    parser.add_argument("--repo", default=_MF6_REPO_NAME)
    parser.add_argument(
        "--ref",
        default=None,
        help="Git ref (branch, tag, or commit) to fetch DFNs from.",
    )
    parser.add_argument(
        "--dfnpath",
        default=None,
        help="Path to a local directory of v1 .dfn files.",
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
        "--no-format",
        action="store_true",
        help="Skip ruff formatting.",
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

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    try:
        generate_classes(
            owner=args.owner,
            repo=args.repo,
            ref=args.ref,
            dfnpath=args.dfnpath,
            outdir=args.outdir,
            developmode=args.developmode,
            fmt=not args.no_format,
            makedirs=args.makedirs,
            existing_only=args.existing_only,
        )
    except (EOFError, KeyboardInterrupt):
        sys.exit(f"Cancelled '{sys.argv[0]}'")


if __name__ == "__main__":
    cli_main()
