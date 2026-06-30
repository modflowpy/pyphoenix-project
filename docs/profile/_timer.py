"""Shared timing utilities for profile scripts (reads and writes)."""

import argparse
import json
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

SLOW_THRESHOLD = 30.0  # seconds — skip remaining runs if first run exceeds this


def make_parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument(
        "--runs",
        type=int,
        default=5,
        help="number of timed repetitions per variant (default: 5)",
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
    p.add_argument(
        "--flopy4-only",
        action="store_true",
        help="skip all flopy3 variants (useful for optimisation iteration)",
    )
    p.add_argument(
        "--profile",
        action="store_true",
        help="run cProfile on the first flopy4 list variant and print top-20 cumulative stats",
    )
    p.add_argument(
        "--memory",
        action="store_true",
        help="measure peak heap memory via tracemalloc for each variant",
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
            f"(skipping remaining {n - 1} runs — use --include-slow to override)"
        )
        return times

    for _ in range(n - 1):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return times


# Semantic alias: reads and writes share the same timing mechanics.
time_reads = time_writes


def profile_memory(fn, label: str) -> dict:
    """Run fn() once and return peak heap allocation in MiB (via tracemalloc).

    Note: tracemalloc tracks Python-managed allocations only. For a full
    native-heap view (e.g. NumPy buffers allocated outside Python), use memray.
    """
    tracemalloc.start()
    try:
        fn()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    peak_mib = peak / (1024**2)
    print(f"  {label:<40}  peak={peak_mib:.1f} MiB")
    return {"label": label, "peak_mib": round(peak_mib, 2)}


def sweep_chunks(
    fn_factory,
    chunk_sizes: list[int],
    label_prefix: str,
    n: int = 3,
    include_slow: bool = False,
) -> list[dict]:
    """Benchmark fn_factory(chunk_size)() across each chunk_size.

    fn_factory(chunk_size) must return a zero-argument callable that exercises
    the operation under test with that chunk size.  Returns a list of result
    dicts in the same format as report().
    """
    results = []
    for cs in chunk_sizes:
        label = f"{label_prefix} [chunks={cs}]"
        fn = fn_factory(cs)
        times = time_writes(fn, n, label, include_slow)
        results.append(report(label, times))
    return results


def profile_fn(fn, label: str, n_lines: int = 20) -> None:
    """Run fn() once under cProfile and print the top n_lines cumulative stats."""
    import cProfile
    import io
    import pstats

    print(f"\n--- cProfile: {label} ---")
    pr = cProfile.Profile()
    pr.enable()
    fn()
    pr.disable()
    buf = io.StringIO()
    pstats.Stats(pr, stream=buf).sort_stats("cumulative").print_stats(n_lines)
    print(buf.getvalue())


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
