"""Top-level CLI entry point for flopy4."""

import argparse
import logging
import shutil
import sys


def _cmd_sync(args: argparse.Namespace) -> None:
    from flopy4.mf6._sync import sync

    result = sync(
        args.release_id,
        mf6_version=args.mf6_version,
        all_packages=args.all_packages,
        force=args.force,
        verbose=args.verbose,
    )
    print(f"Generated {len(result.files)} component modules")
    if result.version != "unknown":
        print(f"Synced flopy4.mf6 to MF6 version: {result.version}")


def _cmd_status(args: argparse.Namespace) -> None:
    try:
        from flopy4.mf6._contract import MF6_VERSION
    except ImportError:
        MF6_VERSION = "unknown"

    from flopy4.mf6._compat import _query_mf6_version

    exe = shutil.which("mf6") or shutil.which("mf6.exe")
    binary_version = _query_mf6_version(exe) if exe else None

    print(f"flopy4.mf6 synced to : {MF6_VERSION}")
    if not exe:
        print("Discovered binary    : (not found on PATH)")
    elif binary_version is None:
        print(f"Discovered binary    : {exe}  (version unknown)")
    else:
        synced = binary_version == MF6_VERSION and MF6_VERSION != "unknown"
        status = "(✓ in sync)" if synced else "(! mismatch)"
        print(f"Discovered binary    : {binary_version}  [{exe}]  {status}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="flopy4")
    sub = parser.add_subparsers(dest="command")

    mf6_p = sub.add_parser("mf6", help="MF6 sync and status commands.")
    mf6_sub = mf6_p.add_subparsers(dest="subcommand")

    # flopy4 mf6 sync
    sync_p = mf6_sub.add_parser(
        "sync",
        help="Sync flopy4.mf6 to an MF6 release: regenerate classes.",
    )
    sync_p.add_argument(
        "release_id",
        nargs="?",
        default=None,
        help="Remote release ID (owner/repo@ref), bare ref, or local path to .dfn files. "
        "Defaults to the discovered binary's version, or latest if no binary found.",
    )
    sync_p.add_argument(
        "--mf6-version",
        default=None,
        dest="mf6_version",
        help="Override MF6 version in _contract.py (useful with local DFN paths).",
    )
    sync_p.add_argument(
        "--no-install",
        action="store_true",
        help="Skip binary installation; regenerate classes only.",
    )
    sync_p.add_argument(
        "--all-packages",
        action="store_true",
        dest="all_packages",
        help="Generate all packages, including ones not yet on disk. "
        "By default sync only updates already-generated files.",
    )
    sync_p.add_argument(
        "--force", action="store_true", help="Re-fetch remote DFNs even if they are cached."
    )
    sync_p.add_argument("--verbose", action="store_true")
    sync_p.set_defaults(func=_cmd_sync)

    # flopy4 mf6 status
    status_p = mf6_sub.add_parser(
        "status",
        help="Show current sync state: synced version vs. discovered binary.",
    )
    status_p.set_defaults(func=_cmd_status)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    if getattr(args, "verbose", False):
        logging.basicConfig(level=logging.INFO)

    args.func(args)


if __name__ == "__main__":
    main()
