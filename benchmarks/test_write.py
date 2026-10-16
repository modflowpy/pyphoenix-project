"""Simulation write benchmarks: flopy3 (`write_simulation`) vs. flopy4
(`Simulation.write`).

Each round writes already-loaded simulations into fresh, empty
directories; loading isn't timed. Only models whose output round-trips
with both libraries are written (see `write_models` in `conftest.py`).

Benchmarks, each parametrized by library:

- `test_write` -- write every model.
- `test_write_largest` -- the same, per model, for the `N_LARGEST` models
  by input bytes.

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
N_LARGEST = 5


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
@pytest.mark.parametrize("rank", range(1, N_LARGEST + 1), ids=lambda r: f"largest{r}")
def test_write_largest(benchmark, write_models, quiet, tmp_path, rank, library):
    """Write each of the largest models (by input bytes) on its own."""
    ranked = sorted(write_models.models, key=lambda m: -m.n_bytes)
    if rank > len(ranked):
        pytest.skip(f"only {len(ranked)} models")
    model = ranked[rank - 1]
    benchmark.group = f"write-largest{rank}"
    benchmark.extra_info.update(model=model.name, **write_models.info(library, [model]))
    _bench_write(benchmark, tmp_path, library, [model])
