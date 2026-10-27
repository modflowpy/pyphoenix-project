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

from _models import TIERS

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

# what each tier holds; a model in several tiers' runs is listed under the
# first of its tiers here
TIER_CONTENTS = {
    "smoke": "a few small models",
    "standard": "the smoke models, plus mid-size ones",
    "large": "big models only, none of smoke's or standard's",
    "full": "the `models-full.txt` manifest",
}

# what the models with each `models.toml` tag have in common
GROUPS = {
    "array": "large gridded arrays",
    "list": "large stress-period lists",
    "external": "data in external files",
    "exg": "exchanges between models",
    "sfr": "an SFR package",
    "lak": "a LAK package",
}
RENAMED_TAGS = {"openclose": "external"}  # in runs saved before the rename

OPS = {"load": "load", "load-materialize": "load + materialize", "write": "write"}


def tier_rank(tier: str) -> int:
    return list(TIER_CONTENTS).index(tier) if tier in TIER_CONTENTS else len(TIER_CONTENTS)


class Results(NamedTuple):
    # (op, model, library) -> minimum seconds, or peak bytes
    times: dict[tuple[str, str, str], float]
    peaks: dict[tuple[str, str, str], float]
    # op -> tier -> library -> (minimum seconds, extra_info), for whole tiers
    totals: dict[str, dict[str, dict[str, tuple[float, dict]]]]
    written: dict[tuple[str, str], int]  # (model, library) -> bytes written
    models: dict[str, dict]  # model -> {"tags", "n_bytes", "tier"}
    cold: dict[str, tuple[float, dict]]  # library -> (wall, extra_info + tier)
    # group -> tier -> parser -> (minimum seconds, extra_info)
    parse: dict[str, dict[str, dict[str, tuple[float, dict]]]]
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
        defaultdict(lambda: defaultdict(dict)),
        {},
        defaultdict(dict),
    )

    def add_model(model: str, tags: list[str], n_bytes: int, tier: str) -> None:
        old = res.models.get(model)
        if old and tier_rank(old["tier"]) <= tier_rank(tier):
            tier = old["tier"]
        tags = [RENAMED_TAGS.get(t, t) for t in tags]
        res.models[model] = {"tags": tags, "n_bytes": n_bytes, "tier": tier}

    for run in sorted(runs, key=lambda r: r.datetime):  # newer runs win
        for b in run.data["benchmarks"]:
            if run.kind == "memory":
                if b["op"] == "import":
                    res.imports[b["library"]] = b
                    continue
                key = (b["op"], b["model"], b["library"])
                res.peaks[key] = b["peak_memory"]
                add_model(b["model"], b["tags"], b["n_bytes"], run.tier)
                continue
            group, params, info = b["group"], b.get("params") or {}, b["extra_info"]
            if b["fullname"].startswith(PROFILE):
                variant = b["name"].partition("[")[2].rstrip("]") or b["name"]
                res.scenarios[group][variant] = b["stats"]
                continue
            t = b["stats"]["min"]
            if "parser" in params or group == "typed-grammar-build":
                res.parse[group][run.tier][params.get("parser", "typed")] = (t, info)
                continue
            library = params["library"]
            if group == "load-cold":
                res.cold[library] = (t, info | {"tier": run.tier})
            elif ":" in group:  # per model
                op, model = group.split(":")[0], info["model"]
                res.times[op, model, library] = t
                add_model(model, info["tags"], info["n_bytes"], run.tier)
                if "n_bytes_written" in info:
                    res.written[model, library] = info["n_bytes_written"]
            else:
                res.totals[group][run.tier][library] = (t, info)
    return res


def by_library(d: dict, op: str, model: str) -> tuple:
    return tuple(d.get((op, model, lib)) for lib in LIBRARIES)


def report(runs: list[Run]) -> str:
    res = collect(runs)
    models = sorted(
        res.models, key=lambda m: (tier_rank(res.models[m]["tier"]), res.models[m]["n_bytes"])
    )
    out = ["# flopy4 vs. flopy3 benchmarks", ""]
    out += runs_table(runs)
    out += [
        "",
        "Times are the minimum over rounds, in seconds. Memory is peak heap",
        "use in MiB, measured with memray. Each × column is flopy3 / flopy4,",
        "so above 1 means flopy4 is faster or uses less memory.",
    ]
    out += tiers_section(res, runs)

    out += op_section(
        res,
        models,
        "load",
        [
            "Loading each simulation, without accessing its data afterward.",
            "The two libraries don't do the same work here. flopy4 reads every",
            "input file at load. flopy3 reads external array files (`OPEN/CLOSE`)",
            "only when their data is accessed, and again on every access, since it",
            "doesn't cache them. So on models with external arrays, flopy3 has",
            "done less work by the end of a load; see load + materialize for the",
            "like-for-like comparison.",
        ],
    )
    out += op_section(
        res,
        models,
        "load-materialize",
        [
            "Loading each simulation, then accessing every array and list and",
            "summing its values, so both libraries have read all of the input.",
            "This is the like-for-like comparison of reading: a model is only",
            "benchmarked if both libraries, by the end, opened exactly the same",
            "files (see `docs/dev/load-benchmarks.md`).",
        ],
    )
    out += op_section(
        res,
        models,
        "write",
        [
            "Writing an already-loaded simulation to an empty directory (the",
            "load isn't timed). flopy3 writes roughly twice the bytes for the",
            "same data, since it pads every value, so part of the difference is",
            "output size. flopy3 also reads its external array files again to",
            "write them, which is left in, since a flopy3 user pays for it too.",
        ],
    )
    out += memory_section(res, models)
    out += groups_section(res, models)

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
        info = next(iter(res.cold.values()))[1]
        out += ["", "## Cold start", ""]
        out += [
            "A fresh interpreter: import the library, then load + materialize",
            f"`{short(info.get('model', ''))}` (from the {info['tier']} tier's run).",
            "Wall time is the minimum over rounds; the split is measured inside",
            "the interpreter, in its last round.",
            "",
        ]
        rows = []
        for lib in LIBRARIES:
            if lib in res.cold:
                t, info = res.cold[lib]
                parts = [secs(info.get(k)) for k in ("import", "load", "materialize")]
                rows.append([lib, secs(t), *parts])
        out += table(["library", "wall", "import", "load", "materialize"], rows)

    out += parse_section(res)

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


def tiers_section(res: Results, runs: list[Run]) -> list[str]:
    tiers = sorted({r.tier for r in runs if r.tier != "profile"}, key=tier_rank)
    if not tiers:
        return []
    rows = []
    for tier in tiers:
        info = next(
            (
                libs[lib][1]
                for libs in (o.get(tier, {}) for o in res.totals.values())
                for lib in libs
            ),
            None,
        )
        if info:
            n, size = info.get("n_models"), info.get("n_bytes")
        else:  # memory runs only
            members = [m for m in res.models if res.models[m]["tier"] in TIERS.get(tier, (tier,))]
            n, size = len(members), sum(res.models[m]["n_bytes"] for m in members)
        rows.append([tier, TIER_CONTENTS.get(tier, ""), str(n or ""), mb(size)])
    out = ["", "The models come in tiers, from `benchmarks/models.toml`:", ""]
    out += table(["tier", "contents", "models", "input MB"], rows, right=2)
    out += [
        "",
        "Timings come for whole tiers, each tier timed as one benchmark,",
        "and for single models, labeled with the tier they belong to.",
    ]
    return out


def op_section(res: Results, models: list[str], op: str, blurb: list[str]) -> list[str]:
    totals = res.totals.get(op, {})
    members = [m for m in models if any(by_library(res.times, op, m))]
    if not totals and not members:
        return []
    out = ["", f"## {OPS[op].capitalize()}", "", *blurb]
    if totals:
        rows = []
        for tier in sorted(totals, key=tier_rank):
            libs = totals[tier]
            (t3, i3), (t4, _) = libs.get("flopy3", (None, {})), libs.get("flopy4", (None, {}))
            rows.append(
                [
                    tier,
                    str(i3.get("n_models", "")),
                    mb(i3.get("n_bytes")),
                    secs(t3),
                    secs(t4),
                    ratio(t3, t4),
                ]
            )
        out += ["", "Whole tiers:", ""]
        out += table(["tier", "models", "input MB", "flopy3", "flopy4", "×"], rows, right=1)
    if members:
        written = op == "write" and res.written
        rows = []
        for m in members:
            t = by_library(res.times, op, m)
            cells = [*model_cells(res, m), secs(t[0]), secs(t[1]), ratio(*t)]
            if written:
                cells += [mb(res.written.get((m, lib))) for lib in LIBRARIES]
            rows.append(cells)
        header = ["model", "tier", "group", "input MB", "flopy3", "flopy4", "×"]
        if written:
            header += ["MB written, flopy3", "flopy4"]
        out += ["", "Single models:", ""]
        out += table(header, rows, right=3)
    return out


def model_cells(res: Results, model: str) -> list[str]:
    m = res.models[model]
    return [short(model), m["tier"], ", ".join(m["tags"]), mb(m["n_bytes"])]


def memory_section(res: Results, models: list[str]) -> list[str]:
    if not res.peaks:
        return []
    notes = {
        "load": "The loaded simulation is kept, so this is at least its footprint.",
        "load-materialize": (
            "Includes what flopy3 reads from external array files on access,"
            " though it doesn't keep it."
        ),
        "write": "Writing an already-loaded simulation.",
    }
    out = ["", "## Peak memory", ""]
    out += [
        "Peak heap use per model, in MiB, from a memray session of its own",
        "(`bench-memory`). Each peak is what the operation allocated, numpy",
        "and pandas included, but not the interpreter or the imports.",
    ]
    for op, name in OPS.items():
        rows = []
        for m in models:
            p = by_library(res.peaks, op, m)
            if any(p):
                rows.append([*model_cells(res, m), mib(p[0]), mib(p[1]), ratio(*p)])
        if rows:
            out += ["", f"### {name.capitalize()}", "", notes[op], ""]
            header = ["model", "tier", "group", "input MB", "flopy3", "flopy4", "×"]
            out += table(header, rows, right=3)
    return out


def groups_section(res: Results, models: list[str]) -> list[str]:
    """Geometric-mean ratios over the models in each group (tag)."""
    columns = [
        ("load + materialize time", res.times, "load-materialize"),
        ("write time", res.times, "write"),
        ("load + materialize memory", res.peaks, "load-materialize"),
        ("write memory", res.peaks, "write"),
    ]
    columns = [c for c in columns if any(k[0] == c[2] for k in c[1])]
    if not columns:
        return []
    tags = sorted({t for m in models for t in res.models[m]["tags"]})
    rows = []
    for tag in ["all", *tags, "none"]:
        if tag == "all":
            members, what = models, "every model"
        elif tag == "none":
            members = [m for m in models if not res.models[m]["tags"]]
            what = "models in no group"
        else:
            members = [m for m in models if tag in res.models[m]["tags"]]
            what = GROUPS.get(tag, "")
        if not members:
            continue
        tiers = sorted({res.models[m]["tier"] for m in members}, key=tier_rank)
        cells = [tag, what, ", ".join(tiers), str(len(members))]
        for _, d, op in columns:
            pairs = [by_library(d, op, m) for m in members]
            g = geomean([a / b for a, b in pairs if a and b])
            cells.append("" if g is None else f"{g:.2f}")
        rows.append(cells)
    out = ["", "## Model groups", ""]
    out += [
        "The models are grouped by what they have in common, mostly what",
        "dominates their input, with tags in `benchmarks/models.toml`. A model",
        "can be in more than one group, or none. Each cell is the geometric",
        "mean of the group's single-model × values, over every tier in this",
        "report; for a one-model group, it's just that model's.",
        "",
    ]
    header = ["group", "models with", "tiers", "models", *(c[0] for c in columns)]
    return out + table(header, rows, right=3)


def parse_section(res: Results) -> list[str]:
    if not res.parse:
        return []
    labels = {
        "parse": "parse",
        "parse-transform": "parse + transform",
        "typed-grammar-build": "typed grammar build",
    }
    rows = []
    for group in res.parse:
        for tier in sorted(res.parse[group], key=tier_rank):
            ts = res.parse[group][tier]
            basic, typed = (ts.get(p, (None, {}))[0] for p in ("basic", "typed"))
            info = next(iter(ts.values()))[1]
            rows.append(
                [
                    labels.get(group, group),
                    tier,
                    str(info.get("n_files", "")),
                    mb(info.get("n_bytes")),
                    secs(basic),
                    secs(typed),
                    ratio(typed, basic),
                ]
            )
    out = ["", "## Lark parser, basic vs. typed", ""]
    out += [
        "flopy4 only. flopy4 has two Lark grammars for MF6 input: the basic",
        "one, which loading uses, and the typed one, generated from the DFNs,",
        "which loading doesn't use yet. Each benchmark runs over every package",
        "file of the tier's models that both grammars accept, read into memory",
        "beforehand, so no file I/O is timed. The last column is typed / basic,",
        "so above 1 means the typed parser is slower.",
        "",
        "- **parse**: lexing and parsing only. The basic parser transforms as",
        "  it parses, so for it this includes the transform.",
        "- **parse + transform**: parsing, then turning the parse tree into",
        "  Python values (`loads_basic` / `loads_typed`).",
        "- **typed grammar build**: building the typed parsers, which happens",
        "  once per process and isn't in the other two.",
        "",
    ]
    header = ["stage", "tier", "files", "input MB", "basic", "typed", "typed / basic"]
    return out + table(header, rows, right=2)


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
