"""
Run all write-time profile scripts and optionally write a formatted report.

Usage
-----
    python run_all.py                         # 5 runs each, no output file
    python run_all.py --runs 3                # 3 runs each
    python run_all.py --output results.json   # save JSON
    python run_all.py --report report.md      # save Markdown table
    python run_all.py --include-slow          # don't skip slow variants
    python run_all.py --models-root /path/to/modflow6-largetestmodels
    python run_all.py --flopy4-only           # skip flopy3 variants in all scripts

Scripts run (in order):
    ff_write.py        frenchman-flat  (~12 variants)
    test1000_write.py  test1000_751x751  3 scenarios
    test1005_write.py  test1005_secp     1 scenario
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
SCRIPTS = [
    ("ff_write.py", "frenchman-flat", False),
    ("test1000_write.py", "test1000_751x751", True),
    ("test1005_write.py", "test1005_secp", True),
]


def run_script(
    script: Path,
    runs: int,
    include_slow: bool,
    json_out: Path,
    models_root: Path | None,
    flopy4_only: bool = False,
) -> dict | None:
    cmd = [sys.executable, str(script), "--runs", str(runs), "--output", str(json_out)]
    if include_slow:
        cmd.append("--include-slow")
    if models_root is not None:
        cmd += ["--models-root", str(models_root)]
    if flopy4_only:
        cmd.append("--flopy4-only")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"  [ERROR] {script.name} exited with code {result.returncode}")
        return None
    if json_out.exists():
        return json.loads(json_out.read_text())
    return None


def markdown_table(all_data: list[dict]) -> str:
    lines = []
    for data in all_data:
        script = data.get("script", "?")
        commit = data.get("git_commit", "?")
        ts = data.get("timestamp", "?")[:19].replace("T", " ")
        lines.append(f"\n## {script}  (commit {commit}, {ts})")
        lines.append("")
        lines.append("| Variant | min (s) | mean (s) | runs |")
        lines.append("|---------|--------:|---------:|-----:|")
        for section in data.get("sections", []):
            lines.append(f"| **{section['name']}** | | | |")
            for r in section.get("results", []):
                skipped = r["runs"] == 1 and r["min"] > 30
                suffix = " ⚠ slow" if skipped else ""
                lines.append(
                    f"| &nbsp;&nbsp;{r['label']}{suffix} "
                    f"| {r['min']:.3f} | {r['mean']:.3f} | {r['runs']} |"
                )
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--runs", type=int, default=5, help="timed write repetitions per variant (default: 5)"
    )
    p.add_argument(
        "--output", type=Path, default=None, help="write combined JSON results to this file"
    )
    p.add_argument(
        "--report", type=Path, default=None, help="write Markdown summary table to this file"
    )
    p.add_argument(
        "--include-slow", action="store_true", help="pass --include-slow to all sub-scripts"
    )
    p.add_argument(
        "--only",
        nargs="+",
        metavar="SCRIPT",
        help="run only these script names (e.g. ff_write.py test1000_write.py)",
    )
    p.add_argument(
        "--models-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="root directory of the modflow6-largetestmodels repo "
        "(required for test1000_write.py and test1005_write.py)",
    )
    p.add_argument(
        "--flopy4-only",
        action="store_true",
        help="skip all flopy3 variants in every sub-script",
    )
    args = p.parse_args()

    tmp_dir = HERE / "results" / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    all_data = []
    for fname, label, needs_models_root in SCRIPTS:
        if args.only and fname not in args.only:
            continue
        if needs_models_root and args.models_root is None:
            print(f"\n  [SKIP] {fname} requires --models-root (modflow6-largetestmodels repo)")
            continue
        script = HERE / fname
        if not script.exists():
            print(f"  [SKIP] {fname} not found")
            continue
        print(f"\n{'#' * 60}")
        print(f"# {label}")
        print(f"{'#' * 60}")
        json_out = tmp_dir / f"{script.stem}.json"
        data = run_script(
            script, args.runs, args.include_slow, json_out, args.models_root, args.flopy4_only
        )
        if data:
            all_data.append(data)

    if not all_data:
        print("\nNo results collected.")
        return

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        combined = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "requested_runs": args.runs,
            "scripts": all_data,
        }
        args.output.write_text(json.dumps(combined, indent=2))
        print(f"\nCombined JSON written to {args.output}")

    if args.report:
        md = markdown_table(all_data)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(md)
        print(f"Markdown report written to {args.report}")

    # Always print a compact summary table to stdout
    print(f"\n{'=' * 70}")
    print(f"{'SUMMARY':^70}")
    print(f"{'=' * 70}")
    for data in all_data:
        print(f"\n{data.get('script', '?')}  (commit {data.get('git_commit', '?')})")
        for section in data.get("sections", []):
            print(f"  [{section['name']}]")
            for r in section.get("results", []):
                skipped = r["runs"] == 1 and r["min"] > 30
                tag = "  [slow]" if skipped else ""
                print(f"    {r['label']:<42}  min={r['min']:.3f}s  mean={r['mean']:.3f}s{tag}")


if __name__ == "__main__":
    main()
