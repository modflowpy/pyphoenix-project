"""
Tests for MF6 code generation.

Structured in three layers so each tier can extend naturally:

  1. Unit tests for filters (no DFNs needed).
  2. Spec tests: build_component_spec() against real DFNs, parametrized per tier.
  3. End-to-end: make_all() produces importable Python files.

To add a new tier:
  - Add the DFN names to the appropriate TIER_* list.
  - Add a TestTier*ComponentSpec class parametrized over those names.
  - Add assertions specific to that tier's expected base class / extras.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from modflow_devtools.dfns import load_flat
from modflow_devtools.dfns.dfn2toml import convert as dfn2toml
from modflow_devtools.dfns.schema.v2 import FieldV2

from flopy4.mf6.component import COMPONENTS
from flopy4.mf6.utils.codegen.filters import (
    class_name,
    is_generatable,
    model_abbr,
    module_name,
    output_path,
    py_type,
    safe_name,
    spec_call,
)
from flopy4.mf6.utils.codegen.make import build_component_spec, make_all


# Shared fixtures
@pytest.fixture(scope="session")
def v2_dfn_dir(dfn_path, tmp_path_factory):
    """Convert the session-level v1 DFN directory to v2 TOML once."""
    v2dir = tmp_path_factory.mktemp("dfn_v2")
    dfn2toml(dfn_path, v2dir)
    return v2dir


@pytest.fixture(scope="session")
def all_dfns(v2_dfn_dir):
    """Load all v2 DFNs as a flat dict."""
    return load_flat(v2_dfn_dir)


# Simple tier: Package subclasses with only scalars, arrays, and path records.
# No complex record types, no extra methods, no custom base classes.
SIMPLE_TIER = {
    "gwf-ic": ("Ic", "Package"),
    "gwf-npf": ("Npf", "Package"),
    "gwf-sto": ("Sto", "Package"),
    "gwf-chd": ("Chd", "Package"),
    "gwf-wel": ("Wel", "Package"),
    "gwf-drn": ("Drn", "Package"),
    "gwf-rch": ("Rch", "Package"),
    "gwf-ghb": ("Ghb", "Package"),
    "gwf-evta": ("Evta", "Package"),
    "gwf-oc": ("Oc", "Package"),
    # Tier 1: same patterns as simple tier, newly generated
    "gwf-riv": ("Riv", "Package"),
    "gwf-api": ("Api", "Package"),
    "gwf-ghbg": ("Ghbg", "Package"),
    "gwf-rivg": ("Rivg", "Package"),
    "gwf-chdg": ("Chdg", "Package"),
    "gwf-drng": ("Drng", "Package"),
    "gwf-welg": ("Welg", "Package"),
    # Tier 2: nseg-1 dropped from dims (repeated columns per row, like naux)
    "gwf-evt": ("Evt", "Package"),
    # Tier 5: list sub-tables exploded into column arrays
    "gwf-buy": ("Buy", "Package"),
    "gwf-vsc": ("Vsc", "Package"),
    "gwf-mvr": ("Mvr", "Package"),
}

# Future tiers (not yet implemented):
# DIS_TIER = {"gwf-dis": ("Dis", "DisBase"), ...}
# TDIS_TIER = {"sim-tdis": ("Tdis", "Package"), ...}


# Layer 1: Filter unit tests (no DFNs required)
class TestFilters:
    """Unit tests for Python-side filter functions."""

    @pytest.mark.parametrize(
        "dfn_name, expected",
        [
            ("gwf-ic", "Ic"),
            ("sln-ims", "Ims"),
            ("sim-tdis", "Tdis"),
            ("gwf-chd", "Chd"),
        ],
    )
    def test_class_name(self, dfn_name, expected):
        assert class_name(dfn_name) == expected

    @pytest.mark.parametrize(
        "dfn_name, expected",
        [
            ("gwf-ic", "ic"),
            ("sln-ims", "ims"),
            ("sim-tdis", "tdis"),
        ],
    )
    def test_module_name(self, dfn_name, expected):
        assert module_name(dfn_name) == expected

    @pytest.mark.parametrize(
        "dfn_name, expected",
        [
            ("gwf-ic", "gwf"),
            ("sln-ims", None),
            ("sim-nam", None),
            ("gwf-npf", "gwf"),
        ],
    )
    def test_model_abbr(self, dfn_name, expected):
        assert model_abbr(dfn_name) == expected

    @pytest.mark.parametrize(
        "dfn_name, rel_path",
        [
            ("gwf-ic", "gwf/ic.py"),
            ("sln-ims", "ims.py"),
            ("sim-tdis", "tdis.py"),
        ],
    )
    def test_output_path(self, dfn_name, rel_path):
        root = Path("/root")
        assert output_path(dfn_name, root) == root / rel_path

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("steady-state", "steady_state"),
            ("type", "type_"),
            ("print", "print_"),
            ("nlay", "nlay"),
            ("grb6_filename", "grb6_filename"),
        ],
    )
    def test_safe_name(self, name, expected):
        assert safe_name(name) == expected

    @pytest.mark.parametrize(
        "ftype, shape, optional, expected",
        [
            ("keyword", None, False, "bool"),
            ("keyword", None, True, "bool"),  # keywords never Optional
            ("integer", None, False, "int"),
            ("integer", None, True, "Optional[int]"),
            ("double", None, False, "float"),
            ("double precision", None, False, "float"),
            ("string", None, False, "str"),
            ("double", "(nodes)", False, "NDArray[np.float64]"),
            ("integer", "(nodes)", True, "Optional[NDArray[np.int64]]"),
            ("keyword", "(nper)", True, "Optional[NDArray[np.bool_]]"),
        ],
    )
    def test_py_type(self, ftype, shape, optional, expected):
        f = FieldV2(name="x", type=ftype, block="options", shape=shape, optional=optional)
        assert py_type(f) == expected

    @pytest.mark.parametrize(
        "ftype, shape",
        [
            ("double", "(nodes)"),
            ("integer", "(nodes)"),
            ("keyword", "(nodes)"),
        ],
    )
    def test_py_type_period_array_always_optional(self, ftype, shape):
        """Period arrays get Optional even when DFN marks them required."""
        f = FieldV2(name="x", type=ftype, block="period", shape=shape, optional=False)
        result = py_type(f)
        assert result.startswith(
            "Optional["
        ), f"Expected Optional for period {ftype} array but got {result!r}"

    @pytest.mark.parametrize(
        "ftype, shape, generatable",
        [
            ("keyword", None, True),
            ("double", "(nodes)", True),
            ("integer", None, True),
            ("string", None, True),
            ("record", None, False),  # plain record — not yet supported
            ("recarray", None, False),
            ("keystring", None, False),
        ],
    )
    def test_is_generatable(self, ftype, shape, generatable):
        f = FieldV2(name="x", type=ftype, block="options", shape=shape)
        assert is_generatable(f) == generatable

    def test_is_generatable_file_record(self):
        """A record with a filein/fileout child is generatable as a path."""
        child_in = FieldV2(name="filein", type="keyword", block="options")
        f = FieldV2(
            name="my_filerecord",
            type="record",
            block="options",
            children={"filein": child_in},
        )
        assert is_generatable(f)

    @pytest.mark.parametrize(
        "ftype, shape, check",
        [
            ("keyword", None, lambda s: s.startswith("field(")),
            ("double", "(nodes)", lambda s: s.startswith("array(")),
            ("integer", "(nper)", lambda s: s.startswith("array(")),
        ],
    )
    def test_spec_call_prefix(self, ftype, shape, check):
        f = FieldV2(name="x", type=ftype, block="options", shape=shape)
        assert check(spec_call(f))

    def test_spec_call_file_record(self):
        child = FieldV2(name="fileout", type="keyword", block="options")
        f = FieldV2(
            name="budget_filerecord",
            type="record",
            block="options",
            children={"fileout": child},
        )
        call = spec_call(f)
        assert 'inout="fileout"' in call
        assert "to_path" in call


# Layer 2: ComponentSpec tests against real DFNs
@pytest.mark.parametrize(
    "dfn_name,expected_class,expected_base",
    [(k, v[0], v[1]) for k, v in SIMPLE_TIER.items()],
)
class TestSimpleTierComponentSpec:
    """Verify build_component_spec() for each simple-tier DFN."""

    def _get_dfn(self, dfn_name, all_dfns):
        if dfn_name not in all_dfns:
            pytest.skip(f"{dfn_name} not available in DFN set")
        return all_dfns[dfn_name]

    def test_class_name(self, dfn_name, expected_class, expected_base, all_dfns):
        dfn = self._get_dfn(dfn_name, all_dfns)
        spec = build_component_spec(dfn, root=Path("/fake"))
        assert spec.class_name == expected_class

    def test_base_class(self, dfn_name, expected_class, expected_base, all_dfns):
        dfn = self._get_dfn(dfn_name, all_dfns)
        spec = build_component_spec(dfn, root=Path("/fake"))
        assert spec.base_class == expected_base

    def test_has_fields(self, dfn_name, expected_class, expected_base, all_dfns):
        dfn = self._get_dfn(dfn_name, all_dfns)
        spec = build_component_spec(dfn, root=Path("/fake"))
        assert len(spec.fields) > 0

    def test_imports_include_base(self, dfn_name, expected_class, expected_base, all_dfns):
        dfn = self._get_dfn(dfn_name, all_dfns)
        spec = build_component_spec(dfn, root=Path("/fake"))
        all_imports = "\n".join(
            spec.imports.get("stdlib", [])
            + spec.imports.get("third_party", [])
            + spec.imports.get("flopy4", [])
        )
        assert "xattree" in all_imports
        assert "Package" in all_imports

    def test_outpath(self, dfn_name, expected_class, expected_base, all_dfns):
        root = Path("/fake/mf6")
        dfn = self._get_dfn(dfn_name, all_dfns)
        spec = build_component_spec(dfn, root=root)
        assert spec.outpath == root / "gwf" / f"{expected_class.lower()}.py"


# Layer 2b: List-field expansion
def test_mvr_list_fields_expanded_and_optional(all_dfns):
    """gwf-mvr list sub-tables should expand into per-column FieldSpecs, all Optional."""
    if "gwf-mvr" not in all_dfns:
        pytest.skip("gwf-mvr not in DFN set")
    spec = build_component_spec(all_dfns["gwf-mvr"], root=Path("/fake"))
    field_map = {f.py_name: f for f in spec.fields}

    # Period block columns (from perioddata list field)
    period_cols = ["pname1", "id1", "pname2", "id2", "mvrtype", "value"]
    for col in period_cols:
        assert col in field_map, f"Expected expanded column '{col}' in MVR fields"
        ann = field_map[col].type_annotation
        assert ann.startswith(
            "Optional["
        ), f"Expanded list column '{col}' should be Optional but got {ann!r}"
        assert field_map[col].generatable, f"Expanded column '{col}' should be generatable"

    # Packages block columns (from packages list field)
    pkg_cols = ["pname", "mname"]
    for col in pkg_cols:
        assert col in field_map, f"Expected expanded column '{col}' in MVR fields"
        assert field_map[col].type_annotation.startswith("Optional[")


# Layer 3: End-to-end generation
def test_simple_tier_generates_importable_files(v2_dfn_dir, tmp_path, all_dfns):
    """Run make_all() and verify each simple-tier file is importable with the right class."""
    (tmp_path / "gwf").mkdir()

    skip = {n for n in load_flat(v2_dfn_dir) if n not in SIMPLE_TIER}
    specs = make_all(dfndir=v2_dfn_dir, outdir=tmp_path, fmt=False, skip=skip)

    generated = {s.dfn_name: s for s in specs}

    for dfn_name, (expected_class, _) in SIMPLE_TIER.items():
        if dfn_name not in all_dfns:
            continue  # not in this DFN set, skip gracefully
        if dfn_name not in generated:
            pytest.fail(f"{dfn_name} was expected but not generated")

        spec = generated[dfn_name]
        assert spec.outpath.exists(), f"Missing {spec.outpath}"

        mod_name = f"_codegen_test.{expected_class.lower()}"
        mod_spec = importlib.util.spec_from_file_location(mod_name, spec.outpath)
        mod = importlib.util.module_from_spec(mod_spec)

        # Snapshot COMPONENTS and sys.modules before loading so that the
        # generated class's __init_subclass__ registration doesn't leak
        # into the shared registry used by other tests.
        components_snapshot = dict(COMPONENTS)
        sys_modules_keys = set(sys.modules)
        try:
            mod_spec.loader.exec_module(mod)
        finally:
            COMPONENTS.clear()
            COMPONENTS.update(components_snapshot)
            for key in set(sys.modules) - sys_modules_keys:
                del sys.modules[key]

        assert hasattr(mod, expected_class), f"Class {expected_class} not found in {spec.outpath}"
