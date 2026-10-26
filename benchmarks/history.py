"""Benchmark runs to history entries, for the weekly benchmark job.

Writes the entries ``github-action-benchmark`` keeps a history of (its
``customSmallerIsBetter`` format), from saved timing runs::

    python benchmarks/history.py RUN [RUN ...] -o OUT

Per tier, for each whole-tier operation (load, load + materialize,
write): flopy4's time, and the ratio flopy4 / flopy3. And the cold start's.
The ratio is the headline: both libraries run on the same runner in the
same job, so it's steadier than a time across runners. It's flopy4 /
flopy3, not the report's flopy3 / flopy4, so that smaller is better, as
the history's alerts assume.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from report import collect, read_run


def entries(paths: list[Path]) -> list[dict]:
    runs = [read_run(p) for p in paths]
    res = collect(runs)
    out = []
    for op in ("load", "load-materialize", "write"):
        for tier, libs in res.totals.get(op, {}).items():
            t3, t4 = (libs.get(lib, (None, {}))[0] for lib in ("flopy3", "flopy4"))
            if t4:
                out.append({"name": f"{op} ({tier}): flopy4", "unit": "s", "value": t4})
            if t3 and t4:
                out.append(
                    {"name": f"{op} ({tier}): flopy4 / flopy3", "unit": "ratio", "value": t4 / t3}
                )
    if cold := res.cold.get("flopy4"):
        out.append({"name": "cold start: flopy4", "unit": "s", "value": cold[0]})
    machines = sorted({r.machine for r in runs})
    for e in out:
        e["extra"] = "; ".join(machines)
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("runs", nargs="+", type=Path, help="saved run JSON files")
    parser.add_argument("-o", "--output", type=Path, required=True, help="write here")
    args = parser.parse_args(argv)
    found = entries(args.runs)
    if not found:
        raise SystemExit("no whole-tier timings in the runs")
    args.output.write_text(json.dumps(found, indent=2) + "\n")
    print(f"wrote {len(found)} entries to {args.output}")


if __name__ == "__main__":
    main()
