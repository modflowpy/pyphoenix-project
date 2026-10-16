"""Simulation load benchmarks: flopy3 (`MFSimulation.load`) vs. flopy4
(`Simulation.load`).

Benchmarks, each parametrized by library:

- `test_load` -- load only. Not like-for-like: flopy3 defers ``OPEN/CLOSE``
  arrays (see `_ops.py`).
- `test_load_materialize` -- load, then fetch and sum every array and
  list. **The fair comparison.**
- `test_load_materialize_model` -- the same, per model, where per-model
  differences show; the totals above are dominated by the biggest models.
- `test_cold_start` -- a fresh interpreter per round: import, then load +
  materialize one mid-size model (`COLD_MODEL`). The child's own
  import/load/materialize split goes in `extra_info`.

There's no ``flopy4-typed`` library yet: typed parser output isn't wired
into structuring, so a full typed load doesn't exist. Add it to `_ops.py`
and `LIBRARIES` when it does.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from _ops import LIBRARIES, load, materialize

ROUNDS = 3
COLD_ROUNDS = 5
# a mid-size DISV model (~0.55 MB, 5 packages + an OPEN/CLOSE array);
# the corpus median is ~12 KB, so "mid" is relative to the models that
# take long enough to measure
COLD_MODEL = "mf6/test/test050_circle_island"
WORKER = Path(__file__).parent / "_worker.py"


def _load(library: str, models: list) -> None:
    for m in models:
        load(library, m.ws, m.load_only)


def _load_materialize(library: str, models: list) -> None:
    for m in models:
        materialize(library, load(library, m.ws, m.load_only))


@pytest.mark.parametrize("library", LIBRARIES)
def test_load(benchmark, models, quiet, library):
    """Load only. Not like-for-like: flopy3 defers ``OPEN/CLOSE`` arrays."""
    benchmark.group = "load"
    benchmark.extra_info.update(models.info)
    benchmark.pedantic(
        _load, args=(library, models.models), rounds=ROUNDS, iterations=1, warmup_rounds=1
    )


@pytest.mark.parametrize("library", LIBRARIES)
def test_load_materialize(benchmark, models, quiet, library):
    """Load, then fetch and sum every array and list: the fair comparison."""
    benchmark.group = "load-materialize"
    benchmark.extra_info.update(models.info)
    benchmark.pedantic(
        _load_materialize,
        args=(library, models.models),
        rounds=ROUNDS,
        iterations=1,
        warmup_rounds=1,
    )


@pytest.mark.parametrize("library", LIBRARIES)
def test_load_materialize_model(benchmark, model, quiet, library):
    """Load + materialize of one model."""
    benchmark.group = f"load-materialize:{model.name.rsplit('/', 1)[-1]}"
    benchmark.extra_info.update(model=model.name, n_bytes=model.n_bytes, tags=model.tags)
    benchmark.pedantic(
        _load_materialize, args=(library, [model]), rounds=ROUNDS, iterations=1, warmup_rounds=1
    )


@pytest.mark.parametrize("library", LIBRARIES)
def test_cold_start(benchmark, models, library):
    """Wall time of a fresh interpreter that imports `library`, then loads
    and materializes `COLD_MODEL`. The child's own import/load/materialize
    split (last round) goes in `extra_info`."""
    model = next((m for m in models.models if m.name == COLD_MODEL), None)
    if model is None:
        pytest.skip(f"{COLD_MODEL} not among the benchmark models")
    cmd = [sys.executable, str(WORKER), "cold", library, str(model.ws)]
    if library == "flopy3":
        cmd += model.load_only
    split: dict = {}

    def run():
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        split.update(json.loads(proc.stdout.strip().splitlines()[-1]))

    benchmark.group = "load-cold"
    benchmark.extra_info.update(model=model.name, n_bytes=model.n_bytes, tags=model.tags)
    benchmark.pedantic(run, rounds=COLD_ROUNDS, iterations=1)
    benchmark.extra_info.update(split)
