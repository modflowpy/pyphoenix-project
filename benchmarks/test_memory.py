"""Memory benchmarks: peak memory per library, model and operation.

Run under pytest-memray (``pixi run -e dev bench-memory``, i.e.
``--memray``), in a session of their own: tracking slows everything down,
so these never run alongside the timing benchmarks, and those never run
under ``--memray``. Not on Windows, which memray doesn't support.

memray tracks only the test body, not fixtures, so each test's peak is
what its operation allocated, numpy and pandas included, without the
interpreter or the libraries' imports. A fixture does the operation once
first, untracked, so one-time costs (lazy imports, DFN and parser caches)
don't land on whichever test runs first:

- `test_load` -- load one model; the loaded simulation stays alive to
  the end, so this is at least its footprint.
- `test_load_materialize` -- load, then fetch every array and list.
  flopy3 doesn't cache ``OPEN/CLOSE`` arrays (see `_ops.py`), so what it
  reads there shows up in the peak but isn't held.
- `test_write` -- write an already-loaded model.
- `test_import` -- importing the library, in a fresh interpreter
  (`_worker.py`), where memray can see it; RSS growth goes alongside.

Each test's peak, model, tags and input bytes go to a JSON file in
``.benchmarks/memory/`` (see `conftest.py`).
"""

import gc
import json
import subprocess
import sys
from pathlib import Path

import pytest
from _ops import LIBRARIES, load, materialize, write

WORKER = Path(__file__).parent / "_worker.py"


def _record(record_property, op, library, model) -> None:
    record_property("op", op)
    record_property("library", library)
    record_property("model", model.name)
    record_property("tags", model.tags)
    record_property("n_bytes", model.n_bytes)


@pytest.fixture
def warm(quiet, model, request):
    library = request.node.callspec.params["library"]
    materialize(library, load(library, model.ws, model.load_only))
    gc.collect()  # so the warm-up's garbage isn't freed while tracking


@pytest.mark.parametrize("library", LIBRARIES)
def test_load(record_property, warm, model, library):
    _record(record_property, "load", library, model)
    sim = load(library, model.ws, model.load_only)  # noqa: F841 -- held to the end


@pytest.mark.parametrize("library", LIBRARIES)
def test_load_materialize(record_property, warm, model, library):
    _record(record_property, "load-materialize", library, model)
    sim = load(library, model.ws, model.load_only)
    materialize(library, sim)


@pytest.fixture
def loaded(quiet, write_model, request, tmp_path_factory):
    """`write_model`, loaded and written once (the warm-up)."""
    library = request.node.callspec.params["library"]
    sim = load(library, write_model.ws, write_model.load_only)
    write(library, sim, tmp_path_factory.mktemp("warm"))
    gc.collect()
    return sim


@pytest.mark.parametrize("library", LIBRARIES)
def test_write(record_property, loaded, write_model, tmp_path, library):
    _record(record_property, "write", library, write_model)
    write(library, loaded, tmp_path)


def _worker(*args) -> dict:
    cmd = [sys.executable, str(WORKER), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("library", LIBRARIES)
def test_import(record_property, library):
    record_property("op", "import")
    record_property("library", library)
    # the worker's measurements, not memray's of this process; RSS from an
    # untracked import, since tracking inflates it
    record_property("peak_memory", _worker("import", library)["peak_memory"])
    record_property("rss", _worker("import", library, "rss")["rss"])
