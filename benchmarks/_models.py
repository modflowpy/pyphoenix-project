"""Which models the benchmarks run on: the tiers in `models.toml`, the
`full` manifest, and `KNOWN_PASSING` for discovering a new manifest."""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path
from typing import NamedTuple

PROJ_ROOT = Path(__file__).parents[1]
BENCH_DIR = Path(__file__).parent
FULL_MANIFEST = BENCH_DIR / "models-full.txt"

# each tier includes the tiers listed with it
TIERS = {
    "smoke": ("smoke",),
    "standard": ("smoke", "standard"),
    "large": ("large",),
}


def known_passing() -> frozenset[str]:
    """The models flopy4 loads, from the load-all-models corpus test."""
    path = PROJ_ROOT / "test" / "mf6" / "test_mf6_load_all_models.py"
    spec = importlib.util.spec_from_file_location("_load_all_models", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.KNOWN_PASSING


def _table() -> list[dict]:
    with open(BENCH_DIR / "models.toml", "rb") as f:
        return tomllib.load(f)["model"]


def tier_models(tier: str) -> list[str]:
    """The models in `tier`, in `models.toml` order (`full`: the manifest)."""
    if tier == "full":
        return FULL_MANIFEST.read_text().split()
    return [m["name"] for m in _table() if m["tier"] in TIERS[tier]]


def model_tags() -> dict[str, list[str]]:
    """Each `models.toml` model's tags; models not listed have none."""
    return {m["name"]: m["tags"] for m in _table()}


class Selection(NamedTuple):
    source: str  # the tier, or the manifest path
    names: list[str]
    pinned: bool  # False only when discovering a manifest


def selection(config) -> Selection:
    manifest: Path | None = config.getoption("bench_manifest")
    if manifest is None:
        tier = config.getoption("bench_tier")
        return Selection(tier, tier_models(tier), True)
    if manifest.exists():
        return Selection(str(manifest), manifest.read_text().split(), True)
    return Selection(str(manifest), sorted(known_passing()), False)
