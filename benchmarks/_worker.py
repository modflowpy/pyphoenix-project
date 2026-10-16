"""Fresh-interpreter measurements, for what an in-process benchmark can't see.

Cold start: import one library, then load and materialize one model,
timing each step::

    python benchmarks/_worker.py cold flopy3|flopy4 WS [LOAD_ONLY ...]

It prints one JSON object. Only the standard library and `_ops` (itself
standard library only at module level) are imported before the timer
starts, so the import step times the library alone.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from _ops import import_library, load, materialize, silence


def cold(library: str, ws: Path, load_only: list[str]) -> dict:
    t0 = time.perf_counter()
    import_library(library)
    t1 = time.perf_counter()
    sim = load(library, ws, load_only)
    t2 = time.perf_counter()
    materialize(library, sim)
    t3 = time.perf_counter()
    return {"import": t1 - t0, "load": t2 - t1, "materialize": t3 - t2}


def main(argv: list[str]) -> None:
    command, *args = argv
    if command == "cold":
        library, ws, *load_only = args
        silence()
        print(json.dumps(cold(library, Path(ws), load_only)), flush=True)
    else:
        raise SystemExit(f"unknown command: {command}")


if __name__ == "__main__":
    main(sys.argv[1:])
