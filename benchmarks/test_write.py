"""Simulation write benchmarks: flopy3 (`write_simulation`) vs. flopy4
(`Simulation.write`).

Each round writes already-loaded simulations into fresh, empty
directories; loading isn't timed. Each library's output is first checked
to reload intact (see `write_models` in `conftest.py`).

Benchmarks, each parametrized by library:

- `test_write` -- write every model.
- `test_write_model` -- the same, per model.

`extra_info` records the files and bytes each library writes: flopy3
writes about twice the bytes for the same data (it pads every value), so
part of a write-time difference is output size.

flopy3 doesn't cache ``OPEN/CLOSE`` arrays (see `_ops.py`), so its writes
read those files again each round. That's part of what a flopy3 user pays
to write a loaded simulation, so it's left in.
"""

import shutil
import tempfile

import pytest
from _ops import LIBRARIES, load, write

ROUNDS = 3


def _bench_write(benchmark, tmp_path, library, models):
    sims = [load(library, m.ws, m.load_only) for m in models]
    outs: list[str] = []

    def setup():
        # a fresh empty directory per model per round; drop the last round's
        for out in outs:
            shutil.rmtree(out, ignore_errors=True)
        outs[:] = [tempfile.mkdtemp(dir=tmp_path) for _ in sims]
        return (), {}

    def run():
        for sim, out in zip(sims, outs):
            write(library, sim, out)

    benchmark.pedantic(run, setup=setup, rounds=ROUNDS, iterations=1, warmup_rounds=1)


@pytest.mark.parametrize("library", LIBRARIES)
def test_write(benchmark, write_models, quiet, tmp_path, library):
    benchmark.group = "write"
    benchmark.extra_info.update(write_models.info(library))
    _bench_write(benchmark, tmp_path, library, write_models.models)


@pytest.mark.parametrize("library", LIBRARIES)
def test_write_model(benchmark, write_models, write_model, quiet, tmp_path, library):
    """Write one model."""
    benchmark.group = f"write:{write_model.name.rsplit('/', 1)[-1]}"
    benchmark.extra_info.update(
        model=write_model.name, tags=write_model.tags, **write_models.info(library, [write_model])
    )
    _bench_write(benchmark, tmp_path, library, [write_model])
