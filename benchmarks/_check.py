"""Checks that the benchmarks compare equal work.

`check`: do flopy3 and flopy4 open the same files? Loads and materializes
a model with both libraries, recording the files each opens under the
workspace with an audit hook. A model whose two file sets differ fails
the benchmarks.

`round_trip`: does a library's output hold what it loaded? Writes a model,
reloads the output with the same library, and compares the two. A model
whose round trip fails with either library fails the write benchmarks.

`check`'s audit hook is process-wide and can't be removed, so it runs as a
script in its own interpreter, never in the benchmark process::

    python benchmarks/_check.py WS [WS ...]

It prints one JSON result per workspace.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from _ops import (
    load,
    load_flopy3,
    load_flopy4,
    load_only_for,
    materialize,
    materialize_flopy3,
    materialize_flopy4,
    package_files,
    silence,
    write,
)

_opened: list[str] | None = None


def _audit(event, args):
    if event == "open" and _opened is not None and isinstance(args[0], (str, bytes, os.PathLike)):
        _opened.append(os.path.realpath(os.fsdecode(args[0])))


def check(ws: Path) -> dict:
    """Load and materialize `ws` with both libraries, recording the files
    each opens under `ws`. Equal work means equal file sets."""
    wsr = os.path.realpath(ws)

    def tracked(fn):
        global _opened
        _opened = []
        try:
            out = fn()
        finally:
            opened, _opened = _opened, None
        return out, {os.path.relpath(p, wsr) for p in opened if p.startswith(wsr + os.sep)}

    result: dict = {"ws": str(ws)}
    try:
        sim4, f4 = tracked(lambda: load_flopy4(ws))
        _, f4_mat = tracked(lambda: materialize_flopy4(sim4))
        load_only = load_only_for({name for _, name in package_files(sim4, ws)})
        sim3, f3 = tracked(lambda: load_flopy3(ws, load_only))
        _, f3_mat = tracked(lambda: materialize_flopy3(sim3))
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"[:500]
        return result
    all3, all4 = f3 | f3_mat, f4 | f4_mat
    result.update(
        load_only=load_only,
        only_flopy3=sorted(all3 - all4),
        only_flopy4=sorted(all4 - all3),
        flopy3_at_materialize=sorted(f3_mat - f3),
        flopy4_at_materialize=sorted(f4_mat - f4),
        n_bytes=sum(os.path.getsize(os.path.join(wsr, f)) for f in all4),
    )
    result["equal"] = not result["only_flopy3"] and not result["only_flopy4"]
    return result


def round_trip(library: str, ws: Path, load_only: list[str], out: Path) -> dict:
    """Load `ws`, write it into `out`, reload `out`, and compare what the two
    loads materialize. Also returns the files and bytes written."""
    result: dict = {"library": library}
    try:
        sim = load(library, ws, load_only)
        before = materialize(library, sim)
        write(library, sim, out)
        after = materialize(library, load(library, out, load_only))
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"[:500]
        return result
    files = [p for p in out.rglob("*") if p.is_file()]
    result.update(
        n_files_written=len(files),
        n_bytes_written=sum(p.stat().st_size for p in files),
        equal=before.matches(after),
        before=repr(before),
        after=repr(after),
    )
    return result


def round_trip_reason(result: dict) -> str:
    if "error" in result:
        return f"{result['library']} round trip: {result['error']}"
    return f"{result['library']} round trip: {result['before']} -> {result['after']}"


def exclusion_reason(result: dict) -> str:
    if "error" in result:
        return result["error"]
    return f"only flopy3 opens {result['only_flopy3']}; only flopy4 opens {result['only_flopy4']}"


if __name__ == "__main__":
    silence()
    sys.addaudithook(_audit)
    for ws in sys.argv[1:]:
        print(json.dumps(check(Path(ws))), flush=True)
