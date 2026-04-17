"""flopy4 command-line interface."""

import argparse
import sys
from pathlib import Path


def _cmd_sync(args) -> int:
    from flopy4.mf6.sync import SyncError, sync

    try:
        result = sync(
            version=args.version,
            bindir=Path(args.bindir) if args.bindir else None,
            validate=args.validate,
        )
    except SyncError as e:
        print(f"sync failed: {e}", file=sys.stderr)
        return 1

    print(f"Synced flopy4 to MF6 {result.version}")
    for exe in result.exes:
        print(f"  installed: {exe}")
    if result.validated:
        print("  validated: smoke test passed")
    return 0


def _cmd_status(args) -> int:
    from flopy4.mf6.sync import status

    info = status()
    print(f"contract version : {info['contract_version']}")
    print(f"dfn schema       : {info['dfn_schema_version']}")
    print(f"binary version   : {info['binary_version'] or '(not found)'}")
    print(f"binary path      : {info['binary_path'] or '(not found)'}")
    if info["in_sync"] is None:
        print("status           : unknown (no binary on PATH)")
    elif info["in_sync"]:
        print("status           : in sync")
    else:
        print(
            f"status           : OUT OF SYNC — "
            f"run `flopy4 sync` to regenerate classes for MF6 {info['binary_version']}"
        )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="flopy4",
        description="flopy4 command-line interface",
    )
    subparsers = parser.add_subparsers(dest="command")

    # flopy4 sync
    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync flopy4 to a specific MF6 version.",
    )
    sync_parser.add_argument(
        "--version",
        "-v",
        default=None,
        help="MF6 version to sync to (default: discovered binary's version).",
    )
    sync_parser.add_argument(
        "--bindir",
        "-b",
        default=None,
        help="Directory to install MF6 binary into (default: auto-select).",
    )
    sync_parser.add_argument(
        "--validate",
        action="store_true",
        default=False,
        help="Run a smoke test with the installed binary after syncing.",
    )

    # flopy4 status
    subparsers.add_parser(
        "status",
        help="Show contract version vs discovered binary.",
    )

    args = parser.parse_args()

    if args.command == "sync":
        sys.exit(_cmd_sync(args))
    elif args.command == "status":
        sys.exit(_cmd_status(args))
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
