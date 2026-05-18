"""Shared timing utilities for write-performance profile scripts."""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

SLOW_THRESHOLD = 30.0  # seconds — skip remaining runs if first run exceeds this


def make_parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument(
        "--runs",
        type=int,
        default=5,
        help="number of timed write repetitions per variant (default: 5)",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write JSON results to this file (default: no file output)",
    )
    p.add_argument(
        "--include-slow",
        action="store_true",
        help=f"run all variants even if first run exceeds {SLOW_THRESHOLD:.0f}s",
    )
    p.add_argument(
        "--models-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="root directory of the modflow6-largetestmodels repo "
        "(required by test1000_write.py and test1005_write.py)",
    )
    return p


def time_writes(fn, n: int, label: str, include_slow: bool = False):
    """Run fn() up to n times, return list of elapsed seconds.

    If the first run exceeds SLOW_THRESHOLD and include_slow is False,
    remaining runs are skipped and a warning is printed.
    """
    times = []
    t0 = time.perf_counter()
    fn()
    elapsed = time.perf_counter() - t0
    times.append(elapsed)

    if elapsed > SLOW_THRESHOLD and not include_slow:
        print(
            f"  {'[SLOW]':<6} {label:<38}  {elapsed:.1f}s  "
            f"(skipping remaining {n-1} runs — use --include-slow to override)"
        )
        return times

    for _ in range(n - 1):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return times


def report(label: str, times: list[float]) -> dict:
    mn = min(times)
    mean = sum(times) / len(times)
    skipped = len(times) == 1 and times[0] > SLOW_THRESHOLD
    suffix = "  [slow — only 1 run]" if skipped else ""
    print(f"  {label:<40}  min={mn:.3f}s  mean={mean:.3f}s{suffix}")
    return {"label": label, "min": mn, "mean": mean, "runs": len(times), "times": times}


def write_results(path: Path, script_name: str, runs: int, sections: list[dict]) -> None:
    """Write results as JSON to path."""
    import subprocess

    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        commit = "unknown"

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": commit,
        "script": script_name,
        "requested_runs": runs,
        "sections": sections,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    print(f"\nResults written to {path}")
