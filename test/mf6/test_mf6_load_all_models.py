"""Corpus smoke test: load every model in the modflow-devtools registry.

`test_mf6_namefile_load.py` proves `Simulation.load()` in depth against one
hand-built model, written and read back through flopy4 itself. This widens
the net across the real MF6 test-model corpus `modflow_devtools.models`
exposes, to track how much of *that* corpus the loader actually handles --
files nobody wrote through flopy4, with all the format variation that
implies.

Every model in the registry is parametrized here -- none are silently
skipped. A first survey (2026-09-11, ~130 of ~242 models sampled) found
only ~9% loading cleanly, traced to two root causes and fixed the same
day:

- A blank or comment-only line inside a block body (before `END`, or
  between content lines) broke the basic grammar's block-closing
  recognition (`basic.lark`'s `line` rule required at least one token per
  line, with no rule to absorb an empty one).
- `GRIDDATA` blocks were partly parsed by the generic scalar-options
  handler before the dedicated array parser ever ran, corrupting
  `LAYERED`/`CONSTANT`/`INTERNAL` control records into garbage field
  values -- silently wrong (not just crashing) for every DIS/DISV
  griddata field, since a bare `TOP\n  CONSTANT 0.` value collapsed to
  the boolean flag `True` broadcast as `1.0`. `OPEN/CLOSE` griddata
  arrays weren't read at all.

Fixing both took the full-corpus pass rate from ~9% to ~55% (134/242,
2026-09-11). Two more fixes the same day: `basic.lark` also required a
trailing newline after a block's closing `END <name>` line and at least
one block per file, which plenty of real fixtures don't have (no final
newline at EOF, or a genuinely empty file) -- ~65% (156/242). Then the
griddata/READARRAY-period control-record readers only ever read one
physical line after an `INTERNAL` keyword, silently truncating any array
wrapped across multiple lines (common for large grids) -- ~78% (188/242).
Then a period/list block's row data (e.g. a package's stress period data)
can itself be `OPEN/CLOSE`-redirected to an external file, which wasn't
recognized at all -- ~81% (197/242). Then a variable-width cellid's
element count was inferred purely from row length, overcounting when a
row carries a trailing token the current Item class doesn't model (e.g. a
field dropped from a newer DFN revision than an older fixture predates)
-- now prefers grid dims (DIS/DISV/DISU -> 3/2/1), unambiguous when
available -- ~84% (204/242). Three more, smaller fixes: a `LAYERED`
griddata field not truly per-layer (`delr`/`delc`-shaped, not
`nodes`-shaped) used the grid's per-layer cell count instead of its own
declared length as the read size, overrunning into the next field's row;
a period-array field sourced from a named time-array-series
(`TIMEARRAYSERIES`) or a per-period `AUXILIARY`-named array (both keyed
dynamically, not a declared class field) weren't recognized, corrupting
the next row read as data; an `OPEN/CLOSE`-referenced griddata array file
with comma-separated values and no spaces wasn't split into tokens --
~87% (211/242). Then `basic.lark`'s `word` token allowed a bare `,`
(never split as a separator), so *any* comma-joined values -- not just
`OPEN/CLOSE`-referenced files -- stayed one token; excluding it exposed
that `word`'s character class was, by an unrelated pre-existing quirk (a
`-` sitting where it formed an unintended range), matching a much wider
set of punctuation than its four explicit characters suggested. Rewrote
the class to name that full set explicitly, comma excluded -- ~88%
(212/242). Two final fixes: real MF6 input files can carry non-MF6
legacy content (a classic MODFLOW-2005/NWT flat-format block, an
apparent `mf5to15` conversion leftover) appended after the file's last
real `BEGIN`/`END` block -- `loads()` now falls back to trimming
anything after the last recognized block when the file fails to parse
as written; and a `LAYERED`/`INTERNAL` array's data lines can each carry
their own trailing inline annotation (not just the array's last line) --
per-line collection now stops at the first non-numeric token instead of
taking every token up to a single final-length truncation. Also: a block
name repeating in one file (an apparent duplicate/leftover package
definition, not itself a parse error) now keeps the first occurrence
rather than silently being overwritten by the second -- ~99% (239/242).
Remaining gaps (two fixture-quality issues, judged out of scope) are
cataloged in `load-corpus-gaps.md`, left `xfail`. Models not known to
pass are
`xfail(strict=False)`: a known gap stays invisible noise, a regression in
a model that works today is a hard failure, and a model that starts
working shows up as XPASS -- the signal to promote it into
`KNOWN_PASSING`.

Each known-passing model's package files are also parsed with their typed,
per-component grammars, a parse-level parity check against the basic loader.
They're read off the loaded simulation, so the check shares the one
`Simulation.load()` call rather than loading the model again to list them.

Each known-passing model's loaded values are also checked against a
snapshot (`__snapshots__/test_mf6_load_all_models/`, a JSON file per
model), so a change to what the loader makes of a file shows up as a
failure and, once accepted with `--snapshot-update`, in the diff. See
`_load_digest` for what's recorded.
"""

import hashlib
import json
from pathlib import Path

import attrs
import numpy as np
import pytest
from modflow_devtools.models import copy_to, get_models
from syrupy.extensions.json import JSONSnapshotExtension

from flopy4.mf6.codec.reader import loads_typed
from flopy4.mf6.component import Component
from flopy4.mf6.item_table import ItemTable
from flopy4.mf6.package import Package
from flopy4.mf6.simulation import Simulation

try:
    ALL_MODELS = sorted(get_models())
except Exception:
    ALL_MODELS = []

# Confirmed loadable end-to-end (Simulation.load() completes without
# raising) by the 2026-09-11 corpus survey, after the fixes in
# load-corpus-gaps.md #1-#9 (all gaps found so far, except #11 and #12
# -- see that doc for why those two are left as genuine, deliberate
# xfails) -- up from 12 models before any of them.
KNOWN_PASSING = frozenset(
    {
        "mf6/test/test001a_Tharmonic",
        "mf6/test/test001a_Tharmonic_extlist",
        "mf6/test/test001a_Tharmonic_tabs",
        "mf6/test/test001b_Tlogarithmic",
        "mf6/test/test001c_Tamtlmk",
        "mf6/test/test001d_Tnewton",
        "mf6/test/test001e_Tnewton_2models",
        "mf6/test/test001e_UZF_3lay",
        "mf6/test/test001e_UZF_3layTS",
        "mf6/test/test001e_UZF_TS",
        "mf6/test/test001e_UZF_spring",
        "mf6/test/test001e_noUZF_3lay",
        "mf6/test/test001f_hfb",
        "mf6/test/test001f_hfb-xt3d",
        "mf6/test/test001f_hfb-xt3d-nwt",
        "mf6/test/test001g_MVR",
        "mf6/test/test001g_MVR_transient",
        "mf6/test/test001h_drn_list4",
        "mf6/test/test001h_evt_array1",
        "mf6/test/test001h_evt_array2",
        "mf6/test/test001h_evt_array3",
        "mf6/test/test001h_evt_array4",
        "mf6/test/test001h_evt_list1",
        "mf6/test/test001h_evt_list2",
        "mf6/test/test001h_evt_list3",
        "mf6/test/test001h_evt_list4",
        "mf6/test/test001h_rch_array1",
        "mf6/test/test001h_rch_array2",
        "mf6/test/test001h_rch_array3",
        "mf6/test/test001h_rch_array4",
        "mf6/test/test001h_rch_list1",
        "mf6/test/test001h_rch_list2",
        "mf6/test/test001h_rch_list3",
        "mf6/test/test001h_rch_list4",
        "mf6/test/test001i_gwf-gwf",
        "mf6/test/test001i_multilayer",
        "mf6/test/test003_gwfs",
        "mf6/test/test003_gwfs_disv",
        "mf6/test/test003_gwfs_disv_xt3d",
        "mf6/test/test003_gwfs_obs",
        "mf6/test/test003_gwfs_reduced",
        "mf6/test/test003_gwfs_tr",
        "mf6/test/test004_bcfss",
        "mf6/test/test004_lpfss",
        "mf6/test/test004_lpfss_disv",
        "mf6/test/test004_lpfss_nr",
        "mf6/test/test005_advgw_tidal",
        "mf6/test/test006_2models",
        "mf6/test/test006_2models-XT3D",
        "mf6/test/test006_2models_gnc",
        "mf6/test/test006_2models_mvr_dev",
        "mf6/test/test006_2models_unconf",
        "mf6/test/test006_2models_unconf_nr",
        "mf6/test/test006_2models_unconf_nr_gnc",
        "mf6/test/test006_2models_unconf_tr_nr",
        "mf6/test/test006_gwf3",
        "mf6/test/test006_gwf3_disv",
        "mf6/test/test006_gwf3_disv_ext",
        "mf6/test/test006_gwf3_disv_hani",
        "mf6/test/test006_gwf3_disv_trimesh",
        "mf6/test/test006_gwf3_disv_trimesh2",
        "mf6/test/test006_gwf3_disv_trimesh2-3D_xt3d",
        "mf6/test/test006_gwf3_disv_trimesh2_xt3d",
        "mf6/test/test006_gwf3_disv_trimesh_xt3d",
        "mf6/test/test006_gwf3_disv_xt3d",
        "mf6/test/test006_gwf3_gnc",
        "mf6/test/test006_gwf3_gnc_nr_mfusg",
        "mf6/test/test006_gwf3_nr_mfusg",
        "mf6/test/test006_gwf3_tr",
        "mf6/test/test006_gwf3_tr_nr",
        "mf6/test/test006_gwf3_unconf",
        "mf6/test/test006a_gwf3_disv_thickstrt",
        "mf6/test/test007_75x75",
        "mf6/test/test007_75x75_confined",
        "mf6/test/test009_3lay-disu",
        "mf6/test/test011_mflgr_ex3",
        "mf6/test/test011_mflgr_ex3_sfr",
        "mf6/test/test012_WaterTable",
        "mf6/test/test013_Zaidel",
        "mf6/test/test014_NWTP3High",
        "mf6/test/test014_NWTP3High_mfusg",
        "mf6/test/test014_NWTP3Low",
        "mf6/test/test014_NWTP3Low_MAW",
        "mf6/test/test014_NWTP3Low_MD_dev",
        "mf6/test/test014_NWTP3Low_RCM_dev",
        "mf6/test/test014_NWTP3Low_dev",
        "mf6/test/test015_KeatingLike",
        "mf6/test/test015_KeatingLike-xt3d",
        "mf6/test/test015_KeatingLike-xt3d-rhs",
        "mf6/test/test015_KeatingLike_disu",
        "mf6/test/test015_KeatingLike_disu_mfusg",
        "mf6/test/test016_Keating",
        "mf6/test/test016_Keating_dev",
        "mf6/test/test016_Keating_disu_250",
        "mf6/test/test016_Keating_disu_250_xt3d",
        "mf6/test/test016_Keating_disu_mfusg",
        "mf6/test/test017_Crinkle",
        "mf6/test/test019_VilhelmsenGC",
        "mf6/test/test019_VilhelmsenGF",
        "mf6/test/test019_VilhelmsenLGR",
        "mf6/test/test019_VilhelmsenLGR_nr",
        "mf6/test/test020_NT_EI",
        "mf6/test/test020_NevilleTonkinTransient",
        "mf6/test/test020_NevilleTonkinTransientTS",
        "mf6/test/test020_NevilleTonkinTransientTS2",
        "mf6/test/test020_NevilleTonkinTransient_aniso",
        "mf6/test/test020_NevilleTonkinTransient_constantMAW",
        "mf6/test/test020_NevilleTonkinTransient_cumcond",
        "mf6/test/test020_NevilleTonkinTransient_cumcond_dev",
        "mf6/test/test020_NevilleTonkinTransient_thickstrt",
        "mf6/test/test020_mawconfined",
        "mf6/test/test020_mawconfined_openclose",
        "mf6/test/test021_twri",
        "mf6/test/test023_FlowingWell",
        "mf6/test/test024_Reilly",
        "mf6/test/test024_Reilly_ext",
        "mf6/test/test025_ConstantCV",
        "mf6/test/test025_ConstantCV_perched",
        "mf6/test/test025_VariableCV",
        "mf6/test/test025_Vertically_Staggered",
        "mf6/test/test026_WellReduction",
        "mf6/test/test027_TimeseriesTest",
        "mf6/test/test027_TimeseriesTest_idomain",
        "mf6/test/test028_sfr",
        "mf6/test/test028_sfr_mvr",
        "mf6/test/test028_sfr_mvr_openclose",
        "mf6/test/test028_sfr_rewet",
        "mf6/test/test028_sfr_rewet_drain",
        "mf6/test/test028_sfr_rewet_nr",
        "mf6/test/test028_sfr_rewet_simple",
        "mf6/test/test028_sfr_simple",
        "mf6/test/test029_lgr_parentchild",
        "mf6/test/test029_lgrsfr_parent",
        "mf6/test/test029_lgrsfr_parent_hole",
        "mf6/test/test029_lgrsfr_parentchild",
        "mf6/test/test030_hani_col",
        "mf6/test/test030_hani_col_disu",
        "mf6/test/test030_hani_row",
        "mf6/test/test030_hani_row_disu",
        "mf6/test/test030_hani_xt3d",
        "mf6/test/test030_hani_xt3d_disu",
        "mf6/test/test031_many_gwf",
        "mf6/test/test032_sfr",
        "mf6/test/test033_wtdecay",
        "mf6/test/test034_nwtp2",
        "mf6/test/test034_nwtp2_1d",
        "mf6/test/test035_fhb",
        "mf6/test/test036_twrihfb",
        "mf6/test/test036_twrihfb_5lay",
        "mf6/test/test036_twrihfb_lpf",
        "mf6/test/test036_twrihfb_nr",
        "mf6/test/test036_twrihfb_openclose",
        "mf6/test/test037_mfcp3",
        "mf6/test/test038_idomain",
        "mf6/test/test041_flowdivert",
        "mf6/test/test041_flowdivert_mfusg",
        "mf6/test/test041_flowdivert_nr",
        "mf6/test/test041_flowdivert_nwt_dev",
        "mf6/test/test042_lake0_dev",
        "mf6/test/test042_lake0_embeddedh",
        "mf6/test/test042_lake0_embeddedh_conf",
        "mf6/test/test042_lake0_embeddedh_openclose",
        "mf6/test/test042_lake0_embeddedv",
        "mf6/test/test042_lake0_embeddedv_conf",
        "mf6/test/test042_lake0_embeddedv_dev",
        "mf6/test/test043_drylake_dev",
        "mf6/test/test044_lakebotfill_dev",
        "mf6/test/test045_lake1ss",
        "mf6/test/test045_lake1ss_1layer_alt_dev",
        "mf6/test/test045_lake1ss_1layer_dev",
        "mf6/test/test045_lake1ss_1layer_thickstrt_dev",
        "mf6/test/test045_lake1ss_dev",
        "mf6/test/test045_lake1ss_none_dev",
        "mf6/test/test045_lake1ss_table_dev",
        "mf6/test/test045_lake1tr_dev",
        "mf6/test/test045_lake1tr_nr",
        "mf6/test/test045_lake2tr_dev",
        "mf6/test/test045_lake2tr_il_dev",
        "mf6/test/test045_lake2tr_nr",
        "mf6/test/test045_lake2tr_xsfra_dev",
        "mf6/test/test045_lake2tr_xsfrb_dev",
        "mf6/test/test045_lake2tr_xsfrc_dev",
        "mf6/test/test045_lake2tr_xsfrd_dev",
        "mf6/test/test045_lake2tr_xsfre_dev",
        "mf6/test/test045_lake4ss",
        "mf6/test/test045_lake4ss_cl_dev",
        "mf6/test/test045_lake4ss_dev",
        "mf6/test/test045_lake4ss_il_dev",
        "mf6/test/test045_lake4ss_nr_dev",
        "mf6/test/test045_lake4ss_nr_embedded",
        "mf6/test/test046_periodic_bc",
        "mf6/test/test046_periodic_bc_openclose",
        "mf6/test/test048_lgr3d_conf",
        "mf6/test/test048_lgr3d_unconf",
        "mf6/test/test048_lgr3d_unconfB",
        "mf6/test/test048_lgr3d_unconfC",
        "mf6/test/test048_lgr3d_unconfD",
        "mf6/test/test049_gwfexgrewet",
        "mf6/test/test050_circle_island",
        "mf6/test/test051_uzfp2",
        "mf6/test/test051_uzfp2TS",
        "mf6/test/test051_uzfp2_mvr",
        "mf6/test/test051_uzfp2_nouzf",
        "mf6/test/test051_uzfp2_openclose",
        "mf6/test/test051_uzfp3_aeET_lakmvr_dev",
        "mf6/test/test051_uzfp3_lakmvr_2uzfmodels_dev",
        "mf6/test/test051_uzfp3_lakmvr_dev",
        "mf6/test/test051_uzfp3_lakmvr_nouzf_dev",
        "mf6/test/test051_uzfp3_lakmvr_v2_dev",
        "mf6/test/test051_uzfp3_wellakmvr_v2",
        "mf6/test/test052_uzf_3col",
        "mf6/test/test053_npf-a",
        "mf6/test/test053_npf-a_mfusg",
        "mf6/test/test053_npf-b",
        "mf6/test/test053_npf-b_mfusg",
        "mf6/test/test054_xt3d_whirlsA",
        "mf6/test/test054_xt3d_whirlsB",
        "mf6/test/test054_xt3d_whirlsC",
        "mf6/test/test055_xt3d_lvda-doc-test1",
        "mf6/test/test056_mt3dms_usgs_gwtex_IR_dev",
        "mf6/test/test056_mt3dms_usgs_gwtex_dev",
        "mf6/test/test057_transientchd",
        "mf6/test/test059_mvlake_lak_ss",
        "mf6/test/test061_csub_holly",
        "mf6/test/test061_csub_jacob",
        "mf6/test/test100_ss_ic",
        "mf6/test/test101_fhb",
        "mf6/test/test102_wel_mvr",
        "mf6/test/test103_drn_mvr",
        "mf6/test/test104_riv_mvr",
        "mf6/test/test105_ghb_mvr",
        "mf6/test/test106_tsnodata",
        "mf6/test/test106_tsnodata/alt_model",
        "mf6/test/test120_mv_dis-lgr",
        "mf6/test/test120_mv_dis-lgr_3models",
        "mf6/test/test120_mv_disv_xt3d",
        "mf6/test/test201_gwtbuy-henryCHD",
        "mf6/test/test202_gwtbuy-henryCHDm",
        "mf6/test/test203_gwtbuy-henryGHB",
        "mf6/test/test204_gwtbuy-henryGHBm",
        "mf6/test/test205_gwtbuy-henrytidal",
        # passing in CI as of 2026-10-05
        "mf6/large/test1000_751x751",
        "mf6/large/test1000_751x751_confined",
        "mf6/large/test1001_Peterson",
        "mf6/large/test1002_biscqtg_disv_dev",
        "mf6/large/test1002_biscqtg_disv_gnc_dev",
        "mf6/large/test1002_biscqtg_disv_gnc_nr_dev",
        "mf6/large/test1002_biscqtg_disv_nr_dev",
        "mf6/large/test1002_biscqtg_disv_nr_MD_dev",
        "mf6/large/test1002_biscqtg_disv_nr_RCM_dev",
        "mf6/large/test1003_MNW2_Fig28",
        "mf6/large/test1004_mvlake_lak_ss_dev",
        "mf6/large/test1004_mvlake_lak_tr",
        "mf6/large/test1004_mvlake_laksfr_tr",
        "mf6/large/test1005_secp",
        "mf6/large/test1200_gwtbuy-goswami",
        "mf6/large/test1201_gwtbuy-elderRa60",
        "mf6/large/test2001_gwtbuy-elderRa400",
    }
)


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
        "an old MODFLOW-2005/NWT conversion tool, not a grammar gap. The "
        "rest use legacy BEGIN XMD/DE4 solver blocks with no equivalent in "
        "the current DFN; an unrecognized block name is a parse error by "
        "design (see typed-grammar-corpus-gaps.md), so these are expected "
        "failures, not a gap to close."
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


# model -> reason, for a typed-grammar failure confined to one model's
# fixture. Its typed check must still fail, like a strict xfail, so a fix
# shows up as a failure asking to drop the entry.
KNOWN_TYPED_MODEL_GAPS: dict[str, str] = {
    "mf6/test/test030_hani_col_disu": (
        "model.disu has a CELLDATA block, which isn't in gwf-disu.dfn (MF6 ignores it)"
    ),
}


def _package_files(component: Component, workspace: Path):
    """Every package file under a loaded component (nested ones like
    TS6/OBS6 included) plus its DFN name, as the load resolved them."""
    for child in component._children.values():
        if isinstance(child, Package):
            yield workspace / child.filename, child.dfn_name
        yield from _package_files(child, workspace)


def _check_typed_grammar(model_name: str, files: list[tuple[Path, str]]) -> None:
    """Every package file a known-passing model resolves should parse under
    its typed grammar too, unless its dfn_name is a documented gap."""
    failures = []
    for path, dfn_name in files:
        if dfn_name in KNOWN_TYPED_GAPS:
            continue
        try:
            loads_typed(path.read_text(), dfn_name)
        except Exception as exc:
            failures.append((path.name, dfn_name, repr(exc)))

    if model_name in KNOWN_TYPED_MODEL_GAPS:
        assert failures, (
            f"typed grammar now parses every file in {model_name}; "
            "drop it from KNOWN_TYPED_MODEL_GAPS"
        )
        return
    assert not failures, (
        f"Simulation.load() passed, but the typed grammar failed on undocumented "
        f"file(s) in {model_name}: {failures}"
    )


# a digested value whose JSON is longer than this is replaced by its hash
_DIGEST_INLINE = 200
_DIGEST_NESTED = 4000


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:16]


def _digest(value, workspace: str):
    """``value``, a loaded field's, as JSON-able data that's equal for equal
    values however they're stored: numbers as int64/float64 (or bool)
    arrays, by hash; an ItemTable, or a list of one attrs class' instances,
    by field, as its rows' values; an attrs instance by field. Long values
    collapse to a hash, so the snapshot shows which field changed, not how."""
    if isinstance(value, np.generic):
        value = value.item()  # not numpy's repr, which changes with numpy 2
    if isinstance(value, Component):
        return f"<{type(value).__name__} {value.name}>"  # its own entry
    if isinstance(value, ItemTable):
        return _table(value.item_cls, len(value), value.values, workspace)
    if (
        isinstance(value, list)
        and value
        and attrs.has(cls := type(value[0]))
        and not issubclass(cls, Component)
        and all(type(v) is cls for v in value)
    ):  # as if an ItemTable, so a list read as one digests the same
        return _table(cls, len(value), lambda name: [getattr(v, name) for v in value], workspace)
    if attrs.has(type(value)):
        return {
            "__type__": type(value).__name__,
            **{
                f.name: _digest(getattr(value, f.name), workspace)
                for f in attrs.fields(type(value))
                if not f.name.startswith("_")
            },
        }
    if (
        isinstance(value, (list, tuple))
        and value
        and all(isinstance(v, (int, float, tuple, np.number)) for v in value)
    ):
        try:
            arr = np.asarray(value)
        except ValueError:  # ragged
            pass
        else:
            if arr.dtype.kind in "biuf":
                return _digest(arr, workspace)
    if isinstance(value, np.ndarray):
        kind = value.dtype.kind
        if kind in "iuf":
            arr = np.ascontiguousarray(value, dtype="<f8" if kind == "f" else "<i8")
            return f"{arr.dtype.name}{list(arr.shape)} {_sha1(arr.tobytes())}"
        if kind == "b":
            return f"bool{list(value.shape)} {_sha1(np.ascontiguousarray(value).tobytes())}"
        return _collapse(_digest(value.tolist(), workspace))
    if isinstance(value, dict):
        return _collapse({str(k): _digest(v, workspace) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return _collapse([_digest(v, workspace) for v in value])
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return repr(value)  # exact, and JSON has no nan/inf
    if isinstance(value, Path):
        return value.as_posix().replace(workspace, "<workspace>")
    text = repr(value)
    assert " at 0x" not in text, f"no stable repr for {type(value).__name__}: {text}"
    return text.replace(workspace, "<workspace>")


def _table(cls: type, n: int, values, workspace: str) -> dict:
    """Rows of the attrs class ``cls``, by field, ``values(name)`` each's."""
    return {
        "__table__": cls.__name__,
        "n": n,
        **{
            f.name: _digest(values(f.name), workspace)
            for f in attrs.fields(cls)
            if not f.name.startswith("_")
        },
    }


def _collapse(data):
    """``data``, or its hash if its JSON is long: over `_DIGEST_INLINE`
    for plain values, over `_DIGEST_NESTED` with tables or records in it,
    so those show by field where they can."""
    items = data.values() if isinstance(data, dict) else data
    nested = any(isinstance(v, (dict, list)) for v in items)
    text = json.dumps(data)
    if len(text) <= (_DIGEST_NESTED if nested else _DIGEST_INLINE):
        return data
    return f"{len(text)} chars {_sha1(text.encode())}"


def _load_digest(component: Component, workspace: Path) -> dict:
    """Each component under ``component`` (itself included), by its path of
    names, as its type and its fields' values (see `_digest`), private ones
    like `_stress_period_data` too. Fields left None are omitted, to keep
    the snapshots small."""
    out: dict = {}
    ws = workspace.as_posix()

    def walk(c: Component, path: str) -> None:
        fields = {}
        for f in attrs.fields(type(c)):
            if f.name in ("_parent", "write_context", "_name_given"):
                continue
            value = getattr(c, f.name, None)
            if value is not None:
                fields[f.name] = _digest(value, ws)
        out[path] = {"__type__": type(c).__name__, **fields}
        for name, child in c._children.items():
            walk(child, f"{path}/{name}")

    walk(component, component.name or "sim")
    return out


def _param(model_name: str):
    marks = []
    # the `large` corpus models take from ~10s to ~2min each to load --
    # `slow` so `pytest --smoke` (modflow-devtools) skips them
    if model_name.startswith("mf6/large/"):
        marks.append(pytest.mark.slow)
    if model_name not in KNOWN_PASSING:
        marks.append(
            pytest.mark.xfail(
                reason="not confirmed loadable by Simulation.load() -- corpus survey 2026-09-11",
                strict=False,
            )
        )
    return pytest.param(model_name, marks=marks)


@pytest.mark.skipif(not ALL_MODELS, reason="modflow-devtools model registry unavailable")
@pytest.mark.parametrize("model_name", [_param(m) for m in ALL_MODELS])
def test_load_simulation(tmp_path, model_name, snapshot):
    """`Simulation.load()` should parse, structure, and resolve bindings for
    every package/model/exchange/solution referenced from `mfsim.nam`,
    without raising. For a known-passing model, its package files should
    also parse under their typed grammars (see `_check_typed_grammar`),
    and its loaded values should match its snapshot (see `_load_digest`)."""
    workspace = copy_to(tmp_path, model_name, verbose=False)
    sim_path = workspace / "mfsim.nam"
    if not sim_path.exists():
        pytest.skip(f"no mfsim.nam in {model_name}")

    sim = Simulation.load(sim_path)

    assert isinstance(sim, Simulation)
    assert sim.tdis is not None
    for children in (sim.models, sim.exchanges, sim.solutiongroup):
        assert isinstance(children, list)

    if model_name in KNOWN_PASSING:
        _check_typed_grammar(model_name, list(_package_files(sim, workspace)))
        if hasattr(snapshot, "use_extension"):  # not with --snapshot-disable
            snapshot = snapshot.use_extension(JSONSnapshotExtension)
        assert _load_digest(sim, workspace) == snapshot
