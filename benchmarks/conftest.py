"""Benchmark options and fixtures.

Benchmarks are opt-in: `pytest.ini` passes ``--benchmark-disable``, so
the timing benchmarks skip unless ``--benchmark-enable`` is given (the
pixi ``bench*`` tasks pass it). The memory benchmarks (`test_memory.py`)
run only under ``--memray`` (``bench-memory``), and then alone.

The models come from ``--bench-tier`` (see `models.toml`), or from
``--bench-manifest``. Either way they're pinned: a model that's missing,
doesn't do equal work, or doesn't round-trip fails the run, so a
regression can't quietly shrink what's compared. Only discovery (a
``--bench-manifest`` path that doesn't exist yet) leaves failing models
out, and writes the rest to that path.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import pytest
from _check import exclusion_reason, round_trip, round_trip_reason
from _models import TIERS, model_tags, selection
from _ops import FLOPY3_OPTIONS, LIBRARIES

BENCH_DIR = Path(__file__).parent

# what each check left out, for the terminal summary: check -> model -> reason
_EXCLUDED: dict[str, dict[str, str]] = {}


def pytest_addoption(parser):
    parser.addoption(
        "--bench-tier",
        choices=[*TIERS, "full"],
        default="standard",
        help="Which models to benchmark: a tier from benchmarks/models.toml, "
        "or full (benchmarks/models-full.txt). Default: standard.",
    )
    parser.addoption(
        "--bench-manifest",
        type=Path,
        default=None,
        help="Benchmark the models listed in this file instead of a tier. If "
        "it doesn't exist, discover them from KNOWN_PASSING and write it.",
    )
    parser.addoption(
        "--bench-parse-manifest",
        type=Path,
        default=None,
        help="Parse benchmarks: pin the corpus to this file list, writing "
        "it on first use -- for comparing grammar variants on identical input.",
    )


def pytest_collection_modifyitems(config, items):
    # at collection, so no fixture (model copies, checks) runs for nothing
    memray = config.getoption("memray", False)  # not on Windows
    timing = config.getoption("benchmark_enable") or not config.getoption("benchmark_disable")
    for item in items:
        if item.path.name == "test_memory.py":
            reason = None if memray else "memory benchmarks need --memray"
        elif memray:
            reason = "timing benchmarks don't run under --memray"
        else:
            reason = None if timing else "benchmarks disabled; pass --benchmark-enable"
        if reason:
            item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture
def quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        logging.disable(logging.CRITICAL)
        try:
            yield
        finally:
            logging.disable(logging.NOTSET)


class Model(NamedTuple):
    name: str
    ws: Path
    load_only: list[str]  # flopy3's, matching what flopy4 loads
    n_bytes: int  # input files both libraries open
    tags: list[str]


class Models(NamedTuple):
    source: str
    models: list[Model]
    excluded: dict[str, str]  # model -> reason
    pinned: bool

    @property
    def info(self) -> dict:
        import flopy

        return {
            "models": self.source,
            "n_models": len(self.models),
            "n_bytes": sum(m.n_bytes for m in self.models),
            "n_excluded": len(self.excluded),
            "flopy_version": flopy.__version__,
            "flopy3_options": FLOPY3_OPTIONS,
        }


@pytest.fixture(scope="session")
def models(request, tmp_path_factory) -> Models:
    """The benchmark models, copied from the registry and checked for
    equal work. A model the check rejects fails the session, unless
    discovering a manifest, which leaves it out."""
    from modflow_devtools.models import copy_to

    sel = selection(request.config)
    names = sel.names

    workspaces = {}
    for name in names:
        ws = copy_to(tmp_path_factory.mktemp("bench"), name, verbose=False)
        if ws is not None and (ws / "mfsim.nam").exists():
            workspaces[str(ws)] = (name, ws)
    missing = set(names) - {name for name, _ in workspaces.values()}
    if sel.pinned and missing:
        pytest.fail(f"pinned models not found: {sorted(missing)}")

    # a fresh interpreter, so the audit hook never touches the timed process
    proc = subprocess.run(
        [sys.executable, str(BENCH_DIR / "_check.py"), *workspaces],
        capture_output=True,
        text=True,
        check=True,
    )
    results = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
    assert len(results) == len(workspaces), proc.stderr[-2000:]

    tags = model_tags()
    models, excluded = [], {}
    for result in results:
        name, ws = workspaces[result["ws"]]
        if result.get("equal"):
            models.append(
                Model(name, ws, result["load_only"], result["n_bytes"], tags.get(name, []))
            )
        else:
            excluded[name] = exclusion_reason(result)
    _EXCLUDED["equal work"] = excluded
    if sel.pinned and excluded:
        pytest.fail(f"pinned models don't load with equal work: {excluded}")
    assert models, "no benchmark models"
    if not sel.pinned:
        Path(sel.source).write_text("\n".join(m.name for m in models) + "\n")
    return Models(sel.source, models, excluded, sel.pinned)


def pytest_generate_tests(metafunc):
    # one test per model, for the per-model benchmarks; at collection, so
    # by name: a model left out while discovering a manifest skips
    if "model_name" in metafunc.fixturenames:
        names = selection(metafunc.config).names
        metafunc.parametrize("model_name", names, ids=lambda n: n.rsplit("/", 1)[-1])


def _model(models: list[Model], name: str) -> Model:
    model = next((m for m in models if m.name == name), None)
    if model is None:  # left out while discovering a manifest
        pytest.skip(f"{name} isn't among the benchmark models")
    return model


@pytest.fixture
def model(models, model_name) -> Model:
    return _model(models.models, model_name)


class Written(NamedTuple):
    files: int
    bytes: int


class WriteModels(NamedTuple):
    models: list[Model]
    excluded: dict[str, str]  # model -> reason
    written: dict[tuple[str, str], Written]  # (library, model) -> output size

    def info(self, library: str, models: list[Model] | None = None) -> dict:
        models = self.models if models is None else models
        out = [self.written[library, m.name] for m in models]
        return {
            "n_models": len(models),
            "n_bytes": sum(m.n_bytes for m in models),
            "n_excluded": len(self.excluded),
            "n_files_written": sum(w.files for w in out),
            "n_bytes_written": sum(w.bytes for w in out),
        }


@pytest.fixture(scope="session")
def write_models(models, tmp_path_factory) -> WriteModels:
    """The benchmark models, once each library's output, reloaded, is
    checked to hold what was loaded, so neither library is timed writing
    less than it should. A model that fails fails the session, unless
    discovering a manifest, which leaves it out of the write benchmarks."""
    kept, excluded, written = [], {}, {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        logging.disable(logging.CRITICAL)
        try:
            for m in models.models:
                reasons = []
                for library in LIBRARIES:
                    out = tmp_path_factory.mktemp("round-trip")
                    result = round_trip(library, m.ws, m.load_only, out)
                    if result.get("equal"):
                        written[library, m.name] = Written(
                            result["n_files_written"], result["n_bytes_written"]
                        )
                    else:
                        reasons.append(round_trip_reason(result))
                if reasons:
                    excluded[m.name] = "; ".join(reasons)
                else:
                    kept.append(m)
        finally:
            logging.disable(logging.NOTSET)
    _EXCLUDED["round trip"] = excluded
    if models.pinned and excluded:
        pytest.fail(f"pinned models don't round-trip: {excluded}")
    assert kept, "no models round-trip with both libraries"
    return WriteModels(kept, excluded, written)


@pytest.fixture
def write_model(write_models, model_name) -> Model:
    return _model(write_models.models, model_name)


# memory benchmarks' recorded properties, by test: nodeid -> properties
_MEMORY: dict[str, dict] = {}
_MEMORY_FILE: list[Path] = []


def pytest_runtest_logreport(report):
    if report.when == "call" and report.passed and Path(report.fspath).name == "test_memory.py":
        _MEMORY[report.nodeid] = dict(report.user_properties)


def _commit(root: Path) -> dict:
    def git(*args):
        proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
        return proc.stdout.strip()

    return {"id": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def pytest_sessionfinish(session):
    """Write the memory benchmarks' peaks, with what each measured, to
    ``.benchmarks/memory/``."""
    manager = session.config.pluginmanager.get_plugin("memray_manager")
    if not _MEMORY or manager is None:
        return
    import flopy

    benchmarks = []
    for nodeid, props in _MEMORY.items():
        if "peak_memory" not in props:  # the import test records its own
            result = manager.results.get(nodeid)
            if result is None:
                continue
            props["peak_memory"] = result.peak_memory
        benchmarks.append({"name": nodeid.split("::")[-1], **props})
    root = session.config.rootpath
    now = datetime.now(timezone.utc)
    commit = _commit(root)
    out = root / ".benchmarks" / "memory" / f"{now:%Y%m%d_%H%M%S}_{commit['id'][:8]}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "datetime": now.isoformat(),
        "commit_info": commit,
        "machine_info": {"python": sys.version.split()[0], "platform": sys.platform},
        "models": selection(session.config).source,
        "flopy_version": flopy.__version__,
        "benchmarks": benchmarks,
    }
    out.write_text(json.dumps(data, indent=2) + "\n")
    _MEMORY_FILE.append(out)


def pytest_terminal_summary(terminalreporter):
    for check, excluded in _EXCLUDED.items():
        if not excluded:
            continue
        terminalreporter.section(f"benchmark models excluded: {check}")
        for name, reason in sorted(excluded.items()):
            terminalreporter.line(f"{name}: {reason}")
    for out in _MEMORY_FILE:
        terminalreporter.section("memory benchmarks")
        rows = json.loads(out.read_text())["benchmarks"]
        for row in sorted(rows, key=lambda r: (r["op"], r.get("model", ""), r["library"])):
            model = row.get("model", "").rsplit("/", 1)[-1]
            mib = row["peak_memory"] / 2**20
            terminalreporter.line(f"{row['op']:<17} {model:<32} {row['library']:<7} {mib:9.1f} MiB")
        terminalreporter.line(f"saved: {out}")
