"""Benchmark runs to Markdown.

Report, from the timing runs pytest-benchmark saves (``bench*`` tasks,
``.benchmarks/<machine>/``) and the memory runs (``bench-memory``,
``.benchmarks/memory/``)::

    python benchmarks/report.py [RUN ...] [-o OUT]

With no runs given, it takes the newest run of each tier (the profiling
scenarios, ``bench-profile``, count as a tier of their own), of each kind,
from the newest commit of that kind, so ``bench`` runs of several tiers
at one commit (and their memory runs) make one report. Where runs
overlap on a model, the newer one wins.

Compare two runs of one kind, timing or memory::

    python benchmarks/report.py --compare [BASE NEW] [--memory] [-o OUT]

With no runs given, NEW is the newest run (timing, or memory with
``--memory``) and BASE the newest before it on the same tier.

Ratios are flopy3 / flopy4 throughout, so above 1 means flopy4 is faster
(or smaller); in comparisons, new / base, so below 1 means faster.
Times are the minimum over rounds.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

STORAGE = Path(__file__).parents[1] / ".benchmarks"
MEMORY = STORAGE / "memory"
LIBRARIES = ("flopy3", "flopy4")
PROFILE = "benchmarks/profile/"


class Run(NamedTuple):
    path: Path
    kind: str  # "timing" or "memory"
    data: dict

    @property
    def datetime(self) -> str:
        return self.data["datetime"]

    @property
    def commit(self) -> str:
        info = self.data["commit_info"]
        return info["id"][:8] + (" (dirty)" if info.get("dirty") else "")

    @property
    def tier(self) -> str:
        if self.kind == "memory":
            return self.data["models"]
        benchmarks = self.data["benchmarks"]
        infos = (b["extra_info"] for b in benchmarks)
        tier = next((i["models"] for i in infos if "models" in i), None)
        if tier is None and any(b["fullname"].startswith(PROFILE) for b in benchmarks):
            return "profile"
        return tier or "?"

    @property
    def machine(self) -> str:
        info = self.data["machine_info"]
        if self.kind == "memory":
            return f"{info['platform']}, Python {info['python']}"
        cpu = info.get("cpu", {}).get("brand_raw", info.get("processor", ""))
        return f"{cpu}, {info['system']}, Python {info['python_version']}"


def read_run(path: Path) -> Run:
    data = json.loads(path.read_text())
    benchmarks = data.get("benchmarks", [])
    kind = "timing" if benchmarks and "stats" in benchmarks[0] else "memory"
    return Run(path, kind, data)


def saved_runs(kind: str) -> list[Run]:
    """Saved runs of `kind`, oldest first."""
    if kind == "memory":
        paths = MEMORY.glob("*.json")
    else:
        paths = (p for p in STORAGE.glob("*/*.json") if p.parent != MEMORY)
    runs = [read_run(p) for p in paths]
    return sorted((r for r in runs if r.kind == kind), key=lambda r: r.datetime)


def latest_runs(kind: str) -> list[Run]:
    """The newest run per tier, at the newest commit with a run of `kind`."""
    runs = saved_runs(kind)
    if not runs:
        return []
    commit = runs[-1].data["commit_info"]["id"]
    by_tier = {r.tier: r for r in runs if r.data["commit_info"]["id"] == commit}
    return sorted(by_tier.values(), key=lambda r: r.datetime)


# --- formatting ---


def secs(x: float | None) -> str:
    return "" if x is None else f"{x:.3g}"


def _num(x: float) -> str:
    return f"{x:.3f}" if x < 1 else f"{x:.3g}" if x < 100 else f"{x:.0f}"


def mib(x: float | None) -> str:
    return "" if x is None else _num(x / 2**20)


def mb(x: float | None) -> str:
    return "" if x is None else _num(x / 1e6)


def ratio(a: float | None, b: float | None) -> str:
    return "" if not a or not b else f"{a / b:.2f}"


def pair(a: str, b: str) -> str:
    return f"{a} / {b}" if a or b else ""


def short(model: str) -> str:
    return model.rsplit("/", 1)[-1]


def geomean(xs: list[float]) -> float | None:
    return math.exp(sum(map(math.log, xs)) / len(xs)) if xs else None


def table(header: list[str], rows: list[list[str]], right: int = 1) -> list[str]:
    """A Markdown table; columns from `right` on are right-aligned."""
    align = ["---" if i < right else "---:" for i in range(len(header))]
    return [f"| {' | '.join(r)} |" for r in [header, align, *rows]]


def runs_table(runs: list[Run]) -> list[str]:
    rows = [
        [r.kind, r.tier, f"`{r.commit}`", r.datetime[:16].replace("T", " "), r.machine]
        for r in runs
    ]
    return table(["run", "models", "commit", "date (UTC)", "machine"], rows, right=5)


# --- report ---


class Results(NamedTuple):
    # (op, model, library) -> minimum seconds, or peak bytes
    times: dict[tuple[str, str, str], float]
    peaks: dict[tuple[str, str, str], float]
    # op -> tier -> library -> (minimum seconds, extra_info), for whole tiers
    totals: dict[str, dict[str, dict[str, tuple[float, dict]]]]
    written: dict[tuple[str, str], int]  # (model, library) -> bytes written
    models: dict[str, dict]  # model -> {"tags", "n_bytes"}
    cold: dict[str, tuple[float, dict]]  # library -> (wall, extra_info)
    parse: dict[str, dict[str, float]]  # group -> parser -> minimum seconds
    imports: dict[str, dict]  # library -> {"peak_memory", "rss"}
    scenarios: dict[str, dict[str, dict]]  # group -> variant -> stats


def collect(runs: list[Run]) -> Results:
    res = Results(
        {},
        {},
        defaultdict(lambda: defaultdict(dict)),
        {},
        {},
        {},
        defaultdict(dict),
        {},
        defaultdict(dict),
    )
    for run in sorted(runs, key=lambda r: r.datetime):  # newer runs win
        for b in run.data["benchmarks"]:
            if run.kind == "memory":
                if b["op"] == "import":
                    res.imports[b["library"]] = b
                    continue
                key = (b["op"], b["model"], b["library"])
                res.peaks[key] = b["peak_memory"]
                res.models[b["model"]] = {"tags": b["tags"], "n_bytes": b["n_bytes"]}
                continue
            group, params, info = b["group"], b.get("params") or {}, b["extra_info"]
            if b["fullname"].startswith(PROFILE):
                variant = b["name"].partition("[")[2].rstrip("]") or b["name"]
                res.scenarios[group][variant] = b["stats"]
                continue
            t = b["stats"]["min"]
            if "parser" in params or group == "typed-grammar-build":
                res.parse[group][params.get("parser", "typed")] = t
                continue
            library = params["library"]
            if group == "load-cold":
                res.cold[library] = (t, info)
            elif ":" in group:  # per model
                op, model = group.split(":")[0], info["model"]
                res.times[op, model, library] = t
                res.models[model] = {"tags": info["tags"], "n_bytes": info["n_bytes"]}
                if "n_bytes_written" in info:
                    res.written[model, library] = info["n_bytes_written"]
            else:
                res.totals[group][run.tier][library] = (t, info)
    return res


def by_library(d: dict, op: str, model: str) -> tuple:
    return tuple(d.get((op, model, lib)) for lib in LIBRARIES)


def report(runs: list[Run]) -> str:
    res = collect(runs)
    out = ["# flopy4 vs. flopy3 benchmarks", ""]
    out += runs_table(runs)
    out += [
        "",
        "Times are the minimum over rounds, in seconds; memory is peak heap",
        "use in MiB (memray). Ratios are flopy3 / flopy4: above 1, flopy4 is",
        "faster or smaller.",
    ]

    if res.totals:
        out += ["", "## Totals", "", "Every model of the tier, in one benchmark.", ""]
        rows = []
        for op in ("load", "load-materialize", "write"):
            for tier, libs in res.totals.get(op, {}).items():
                (t3, i3), (t4, _) = libs.get("flopy3", (None, {})), libs.get("flopy4", (None, {}))
                rows.append(
                    [
                        op,
                        tier,
                        str(i3.get("n_models", "")),
                        mb(i3.get("n_bytes")),
                        secs(t3),
                        secs(t4),
                        ratio(t3, t4),
                    ]
                )
        header = ["benchmark", "models", "n", "input MB", "flopy3", "flopy4", "×"]
        out += table(header, rows, right=2)

    models = sorted(res.models, key=lambda m: res.models[m]["n_bytes"])
    if models:
        out += ["", "## Per model", ""]
        if res.times:
            out += [
                "Load + materialize (the fair comparison: flopy3 reads `OPEN/CLOSE`",
                "arrays only on access) and write, in seconds; bytes written in MB.",
                "",
            ]
            rows = []
            for m in models:
                lm, w = (
                    by_library(res.times, "load-materialize", m),
                    by_library(res.times, "write", m),
                )
                if not any(lm + w):
                    continue
                rows.append(
                    [
                        short(m),
                        ", ".join(res.models[m]["tags"]),
                        mb(res.models[m]["n_bytes"]),
                        secs(lm[0]),
                        secs(lm[1]),
                        ratio(*lm),
                        secs(w[0]),
                        secs(w[1]),
                        ratio(*w),
                        pair(*(mb(res.written.get((m, lib))) for lib in LIBRARIES)),
                    ]
                )
            header = [
                "model",
                "tags",
                "input MB",
                "load+mat flopy3",
                "flopy4",
                "×",
                "write flopy3",
                "flopy4",
                "×",
                "written flopy3 / flopy4",
            ]
            out += table(header, rows, right=2)
        if res.peaks:
            out += ["", "Peak memory in MiB, flopy3 / flopy4, and the ratio:", ""]
            ops = ("load", "load-materialize", "write")
            rows = []
            for m in models:
                cells = [short(m), ", ".join(res.models[m]["tags"]), mb(res.models[m]["n_bytes"])]
                for op in ops:
                    p = by_library(res.peaks, op, m)
                    cells += [pair(*map(mib, p)), ratio(*p)]
                if any(cells[3:]):
                    rows.append(cells)
            header = ["model", "tags", "input MB"]
            for op in ops:
                header += [op, "×"]
            out += table(header, rows, right=2)

        out += by_tag(res, models)

    if res.imports:
        out += ["", "## Import", ""]
        out += [
            "Importing each library in a fresh interpreter: peak heap use",
            "(memray), and RSS growth, which also counts extension modules.",
            "",
        ]
        rows = []
        for lib in LIBRARIES:
            b = res.imports.get(lib)
            if b:
                rows.append([lib, mib(b["peak_memory"]), mib(b.get("rss"))])
        out += table(["library", "heap peak MiB", "RSS growth MiB"], rows)

    if res.cold:
        model = next(iter(res.cold.values()))[1].get("model", "")
        out += ["", "## Cold start", ""]
        out += [
            f"A fresh interpreter: import, then load + materialize `{short(model)}`.",
            "Wall time is the minimum over rounds; the split is the child's own,",
            "from its last round.",
            "",
        ]
        rows = []
        for lib in LIBRARIES:
            if lib in res.cold:
                t, info = res.cold[lib]
                parts = [secs(info.get(k)) for k in ("import", "load", "materialize")]
                rows.append([lib, secs(t), *parts])
        out += table(["library", "wall", "import", "load", "materialize"], rows)

    if res.parse:
        out += ["", "## Parse stage, basic vs. typed", ""]
        rows = []
        for group, ts in res.parse.items():
            basic, typed = ts.get("basic"), ts.get("typed")
            rows.append([group, secs(basic), secs(typed), ratio(typed, basic)])
        out += table(["benchmark", "basic", "typed", "typed / basic"], rows)

    if res.scenarios:
        out += ["", "## Profiling scenarios", ""]
        out += ["From `benchmarks/profile/`; times in seconds, fastest first.", ""]
        for group in sorted(res.scenarios):
            stats = sorted(res.scenarios[group].items(), key=lambda kv: kv[1]["min"])
            rows = [[v, secs(st["min"]), secs(st["mean"]), str(st["rounds"])] for v, st in stats]
            out += [f"### {group}", ""]
            out += table(["variant", "min", "mean", "rounds"], rows) + [""]
        out.pop()

    return "\n".join(out) + "\n"


def by_tag(res: Results, models: list[str]) -> list[str]:
    """Geometric-mean ratios over the models with each tag."""
    tags = sorted({t for m in models for t in res.models[m]["tags"]})
    columns = [
        ("load+mat time", res.times, "load-materialize"),
        ("write time", res.times, "write"),
        ("load+mat memory", res.peaks, "load-materialize"),
        ("write memory", res.peaks, "write"),
    ]
    columns = [c for c in columns if any(k[0] == c[2] for k in c[1])]
    if not columns:
        return []
    rows = []
    for tag in ["all", "untagged", *tags]:
        if tag == "all":
            members = models
        elif tag == "untagged":
            members = [m for m in models if not res.models[m]["tags"]]
        else:
            members = [m for m in models if tag in res.models[m]["tags"]]
        if not members:
            continue
        cells = [tag, str(len(members))]
        for _, d, op in columns:
            pairs = [by_library(d, op, m) for m in members]
            g = geomean([a / b for a, b in pairs if a and b])
            cells.append("" if g is None else f"{g:.2f}")
        rows.append(cells)
    out = ["", "## By tag", ""]
    out += [
        "Geometric mean of the per-model ratios (flopy3 / flopy4) over the",
        "models with each tag (see `benchmarks/models.toml`).",
        "",
    ]
    return out + table(["tag", "models", *(c[0] for c in columns)], rows)


# --- comparison ---


def _values(run: Run) -> dict[str, float]:
    if run.kind == "memory":
        return {b["name"]: b["peak_memory"] for b in run.data["benchmarks"]}
    return {b["fullname"].split("::")[-1]: b["stats"]["min"] for b in run.data["benchmarks"]}


def compare(base: Run, new: Run) -> str:
    if base.kind != new.kind:
        raise SystemExit(f"can't compare a {base.kind} run with a {new.kind} run")
    what = "peak memory, MiB" if new.kind == "memory" else "minimum time, seconds"
    fmt = mib if new.kind == "memory" else secs
    out = [f"# Benchmark comparison ({what})", ""]
    out += runs_table([base, new])
    if base.tier != new.tier:
        out += ["", f"**Different models:** base `{base.tier}`, new `{new.tier}`."]
    out += ["", "new / base: below 1 is an improvement.", ""]
    b, n = _values(base), _values(new)
    rows = [[name, fmt(b[name]), fmt(n[name]), ratio(n[name], b[name])] for name in n if name in b]
    out += table(["benchmark", "base", "new", "new / base"], rows)
    for label, names in (
        ("Only in base", b.keys() - n.keys()),
        ("Only in new", n.keys() - b.keys()),
    ):
        if names:
            out += ["", f"{label}: " + ", ".join(f"`{x}`" for x in sorted(names))]
    return "\n".join(out) + "\n"


def default_pair(kind: str) -> tuple[Run, Run]:
    runs = saved_runs(kind)
    if not runs:
        raise SystemExit(f"no saved {kind} runs")
    new = runs[-1]
    earlier = [r for r in runs[:-1] if r.tier == new.tier]
    if not earlier:
        raise SystemExit(f"no earlier {kind} run of {new.tier!r} to compare {new.path.name} with")
    return earlier[-1], new


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("runs", nargs="*", type=Path, help="saved run JSON files")
    parser.add_argument("--compare", action="store_true", help="compare two runs, BASE NEW")
    parser.add_argument("--memory", action="store_true", help="with --compare: memory runs")
    parser.add_argument("-o", "--output", type=Path, help="write here instead of stdout")
    args = parser.parse_args(argv)

    if args.compare:
        if args.runs and len(args.runs) != 2:
            parser.error("--compare takes two runs, BASE NEW, or none")
        if args.runs:
            base, new = map(read_run, args.runs)
        else:
            base, new = default_pair("memory" if args.memory else "timing")
        text = compare(base, new)
    else:
        runs = [read_run(p) for p in args.runs] or latest_runs("timing") + latest_runs("memory")
        if not runs:
            raise SystemExit(f"no saved runs in {STORAGE}")
        text = report(runs)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
        print(f"wrote {args.output}")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
