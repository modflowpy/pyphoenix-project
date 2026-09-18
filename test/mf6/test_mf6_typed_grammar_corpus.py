"""Corpus smoke test: parse every real package file the basic loader already
handles with its typed, per-component grammar too.

Reuses `test_mf6_load_all_models.py`'s `KNOWN_PASSING` corpus (models whose
`Simulation.load()` -- the *basic*, untyped loader -- already completes end
to end) as a source of real, known-good MF6 input text. For each such model,
transiently wraps `Package.load` to capture every child package file it
resolves along with its DFN name (`Package.dfn_name`, e.g. "gwf-wel"), then
re-parses that same file's raw text through the *typed* grammar
(`flopy4.mf6.codec.reader.loads_typed`). The wrapped call still runs the real
`Package.load` underneath -- this only observes what gets resolved, it
doesn't change the basic-path result for this test run.

Unlike `test_mf6_load_all_models.py`'s per-model `xfail`, granularity here is
naturally per-*file* (one model exercises several different package types),
which doesn't fit that file's one-mark-per-parametrized-item idiom. Instead:
a failure for a dfn_name listed in `KNOWN_TYPED_GAPS` (documented in
`typed-grammar-corpus-gaps.md`, one entry per root cause, mirroring
`load-corpus-gaps.md`'s methodology) is tolerated; any *other* dfn_name's
file failing to parse is a hard failure -- either a new, uncataloged gap, or
a regression in one already thought fixed.

Explicitly out of scope (see the plan this test was written under): this
only checks that the typed grammar *parses* the file -- it does not attempt
to transform/structure the result the way `structure_component()` does for
the basic path (dims-aware array reshaping, OPEN/CLOSE row redirection,
AUXILIARY/TIMEARRAYSERIES dynamic fields). Parity here means parse-level
parity only.
"""

from pathlib import Path
from unittest import mock

import pytest
from modflow_devtools.models import copy_to

from flopy4.mf6.codec.reader import loads_typed
from flopy4.mf6.package import Package
from flopy4.mf6.simulation import Simulation

from .test_mf6_load_all_models import KNOWN_PASSING

# dfn_name -> reason, for typed-grammar parse failures already root-caused
# and cataloged in typed-grammar-corpus-gaps.md. Granularity is coarser than
# ideal (per-dfn_name, not per-file): a dfn_name listed here has its files
# skipped *entirely*, even the many files of that type that parse fine, so a
# future regression restricted to those files wouldn't be caught. Accepted
# for now -- refining to per-file skips is real, tracked follow-up work, not
# done this pass (see typed-grammar-corpus-gaps.md's "Corpus test status").
KNOWN_TYPED_GAPS: dict[str, str] = {
    "sln-ims": (
        "2 legacy mf5to6-converted fixtures (test017_Crinkle, "
        "test044_lakebotfill_dev) write two option values on one line for "
        "a field the current DFN defines as a single scalar (e.g. "
        "'preconditioner_levels 0 7') -- a fixture-authoring artifact from "
        "an old MODFLOW-2005/NWT conversion tool, not a grammar gap. "
        "Legacy BEGIN XMD/DE4 solver blocks (no current DFN equivalent) "
        "parse fine via the generic unknown_block fallback."
    ),
    "gwf-npf": (
        "2 files with a free-text remark that happens to contain a "
        'reserved word (e.g. a parenthetical comment mentioning "constant") '
        "-- it loses to that word's keyword literal under Lark's default "
        "priority rules. Fixing this would need per-context lexer modes, "
        "which Lark's LALR contextual lexer doesn't support; very low "
        "frequency (2/2228 files), not pursued this pass."
    ),
    "gwf-lak": (
        "DEV_NO_FINAL_CHECK is not a field in the current gwf-lak.dfn -- "
        "confirmed genuine field-name/version drift (a removed dev option), "
        "not a grammar gap."
    ),
}


def _collect_package_files(sim_path: Path) -> list[tuple[Path, str]]:
    """Run the real `Simulation.load()` (basic path), capturing every child
    package file it resolves plus its DFN name.

    Reuses `_resolve_bindings`'s production token/class-resolution logic
    directly (via the real load path) instead of duplicating it -- the
    wrapper only records calls, `original` still does the actual load.
    """
    calls: list[tuple[Path, str]] = []
    original = Package.load.__func__

    def wrapper(cls, path, dims=None, name=None):
        calls.append((Path(path), cls.dfn_name))
        return original(cls, path, dims=dims, name=name)

    with mock.patch.object(Package, "load", classmethod(wrapper)):
        Simulation.load(sim_path)
    return calls


@pytest.mark.parametrize("model_name", sorted(KNOWN_PASSING))
def test_typed_grammar_parses_known_passing_files(tmp_path, model_name, dfn_path):
    """Every package file a known-passing model resolves should parse under
    its typed grammar too, unless its dfn_name is a documented gap."""
    workspace = copy_to(tmp_path, model_name, verbose=False)
    sim_path = workspace / "mfsim.nam"
    if not sim_path.exists():
        pytest.skip(f"no mfsim.nam in {model_name}")

    files = _collect_package_files(sim_path)
    unexpected_failures = []
    for path, dfn_name in files:
        if dfn_name in KNOWN_TYPED_GAPS:
            continue
        text = path.read_text()
        try:
            loads_typed(text, dfn_name, dfn_path=str(dfn_path))
        except Exception as exc:
            unexpected_failures.append((path.name, dfn_name, repr(exc)))

    assert not unexpected_failures, (
        f"typed grammar failed on undocumented file(s) in {model_name}: {unexpected_failures}"
    )
