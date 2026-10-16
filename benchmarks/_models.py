"""Which models the benchmarks run on."""

from __future__ import annotations

import importlib.util
from pathlib import Path

PROJ_ROOT = Path(__file__).parents[1]


def known_passing() -> frozenset[str]:
    """The models flopy4 loads, from the load-all-models corpus test."""
    path = PROJ_ROOT / "test" / "mf6" / "test_mf6_load_all_models.py"
    spec = importlib.util.spec_from_file_location("_load_all_models", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.KNOWN_PASSING
