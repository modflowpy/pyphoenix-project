"""Benchmark options and fixtures.

Benchmarks are opt-in: `pytest.ini` passes ``--benchmark-disable``, so
every module here skips unless ``--benchmark-enable`` is given (the pixi
``bench*`` tasks pass it).
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import warnings
from pathlib import Path
from typing import NamedTuple

import pytest
from _check import exclusion_reason, round_trip, round_trip_reason
from _models import known_passing
from _ops import FLOPY3_OPTIONS, LIBRARIES

BENCH_DIR = Path(__file__).parent

# what each check left out, for the terminal summary: check -> model -> reason
_EXCLUDED: dict[str, dict[str, str]] = {}


def pytest_addoption(parser):
    parser.addoption(
        "--bench-manifest",
        type=Path,
        default=None,
        help="Pin the benchmark models to this list, writing it on first use, "
        "so later runs time identical input.",
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
    if config.getoption("benchmark_disable") and not config.getoption("benchmark_enable"):
        skip = pytest.mark.skip(reason="benchmarks disabled; pass --benchmark-enable")
        for item in items:
            item.add_marker(skip)


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


class Models(NamedTuple):
    models: list[Model]
    excluded: dict[str, str]  # model -> reason

    @property
    def info(self) -> dict:
        import flopy

        return {
            "n_models": len(self.models),
            "n_bytes": sum(m.n_bytes for m in self.models),
            "n_excluded": len(self.excluded),
            "flopy_version": flopy.__version__,
            "flopy3_options": FLOPY3_OPTIONS,
        }


@pytest.fixture(scope="session")
def models(request, tmp_path_factory) -> Models:
    """The benchmark models, copied from the registry and checked for
    equal work. A model the check rejects is excluded, or fails the
    session if the manifest pins it."""
    from modflow_devtools.models import copy_to

    manifest: Path | None = request.config.getoption("bench_manifest")
    pinned = manifest.read_text().split() if manifest and manifest.exists() else None
    names = pinned if pinned is not None else sorted(known_passing())

    workspaces = {}
    for name in names:
        ws = copy_to(tmp_path_factory.mktemp("bench"), name, verbose=False)
        if ws is not None and (ws / "mfsim.nam").exists():
            workspaces[str(ws)] = (name, ws)
    missing = set(names) - {name for name, _ in workspaces.values()}
    if pinned is not None and missing:
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

    models, excluded = [], {}
    for result in results:
        name, ws = workspaces[result["ws"]]
        if result.get("equal"):
            models.append(Model(name, ws, result["load_only"], result["n_bytes"]))
        else:
            excluded[name] = exclusion_reason(result)
    if pinned is not None and excluded:
        pytest.fail(f"pinned models no longer load with equal work: {excluded}")
    assert models, "no benchmark models"
    if pinned is None and manifest is not None:
        manifest.write_text("\n".join(m.name for m in models) + "\n")
    _EXCLUDED["equal work"] = excluded
    return Models(models, excluded)


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
    """The benchmark models whose output, reloaded, holds what was loaded,
    with both libraries. The others are excluded from write benchmarks, so
    neither library is timed writing less than it should."""
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
    assert kept, "no models round-trip with both libraries"
    return WriteModels(kept, excluded, written)


def pytest_terminal_summary(terminalreporter):
    for check, excluded in _EXCLUDED.items():
        if not excluded:
            continue
        terminalreporter.section(f"benchmark models excluded: {check}")
        for name, reason in sorted(excluded.items()):
            terminalreporter.line(f"{name}: {reason}")
