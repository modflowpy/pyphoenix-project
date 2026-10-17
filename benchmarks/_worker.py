"""Fresh-interpreter measurements, for what an in-process benchmark can't see.

Cold start: import one library, then load and materialize one model,
timing each step::

    python benchmarks/_worker.py cold flopy3|flopy4 WS [LOAD_ONLY ...]

Import memory: what importing one library costs, which a memory benchmark
can't see in a pytest process that already imported both. Its peak heap
use, by memray (as the memory benchmarks measure), or with ``rss``, its
RSS growth, untracked, which also counts mapped extension modules and
shared libraries::

    python benchmarks/_worker.py import flopy3|flopy4 [rss]

Each prints one JSON object. Only the standard library and `_ops` (itself
standard library only at module level) are imported before measuring, so
each measurement covers the library alone.
"""

from __future__ import annotations

import json
import sys
import tempfile
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


def _max_rss() -> int:
    import resource

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss if sys.platform == "darwin" else rss * 1024  # Linux reports KiB


def import_rss(library: str) -> dict:
    rss = _max_rss()
    import_library(library)
    return {"rss": _max_rss() - rss}


def import_peak(library: str) -> dict:
    from memray import FileFormat, FileReader, Tracker

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "import.bin"
        with Tracker(
            path, file_format=FileFormat.AGGREGATED_ALLOCATIONS, trace_python_allocators=True
        ):
            import_library(library)
        return {"peak_memory": FileReader(path).metadata.peak_memory}


def main(argv: list[str]) -> None:
    command, *args = argv
    if command == "cold":
        library, ws, *load_only = args
        silence()
        print(json.dumps(cold(library, Path(ws), load_only)), flush=True)
    elif command == "import":
        library, *what = args
        silence()
        result = import_rss(library) if what == ["rss"] else import_peak(library)
        print(json.dumps(result), flush=True)
    else:
        raise SystemExit(f"unknown command: {command}")


if __name__ == "__main__":
    main(sys.argv[1:])
