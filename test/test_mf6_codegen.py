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
from modflow_devtools.dfn import Dfn, Field

from flopy4.mf6.component import COMPONENTS
from flopy4.mf6.utils.codegen.filters import (
    can_expand_record,
    class_name,
    is_generatable,
    model_abbr,
    module_name,
    output_path,
    py_type,
    safe_name,
    schema_class,
)
from flopy4.mf6.utils.codegen.make import build_component_spec, make_modules


# Shared fixtures
@pytest.fixture(scope="session")
def all_dfns(dfn_path):
    """Load all DFNs as a flat dict."""
    return Dfn.load_all(dfn_path, schema_version="2.0.0.dev1")


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
    # Tier 6: compressible storage
    # (gwf-sfr, gwf-maw excluded: keystring period settings silently absent)
    # (gwf-uzf excluded: duplicated ifno attribute and not currently functional)
    # (gwf-hfb excluded: cell-pair recarray Tier 7, requires framework changes)
    "gwf-csub": ("Csub", "Package"),
}

# Transport model packages: gwt-ist (immobile storage transport, multi=True).
TRANSPORT_TIER = {
    "gwt-ist": ("Ist", "Package", "gwt"),
}

# Tier 1a: OC record expansion — saverecord/printrecord → per-rtype NDArray[np.str_] fields.
# Each tuple is (class_name, base_class, model_prefix).
OC_TIER = {
    "gwt-oc": ("Oc", "Package", "gwt"),
    "gwe-oc": ("Oc", "Package", "gwe"),
    "prt-oc": ("Oc", "Package", "prt"),
}

# Utility packages (utl/), including utl-tas with 3 inner record classes.
UTL_TIER = {
    "utl-ats": ("Ats", "Package"),
    "utl-laktab": ("Laktab", "Package"),
    "utl-ncf": ("Ncf", "Package"),
    "utl-sfrtab": ("Sfrtab", "Package"),
    "utl-spca": ("Spca", "Package"),
    "utl-tas": ("Tas", "Package"),
}

# Exchange packages (exg/) — only zero-field (pass-only) classes.
# Packages with cellidm1/cellidm2 fields (gwfgwf, gwegwe, gwtgwt, olfgwf, chfgwf)
# are excluded: ncelldim resolution is not yet implemented in the ingress/egress layers.
EXG_TIER = {
    "exg-gwfgwe": ("Gwfgwe", "Package"),
    "exg-gwfgwt": ("Gwfgwt", "Package"),
    "exg-gwfprt": ("Gwfprt", "Package"),
}

SOLUTION_TIER = {
    "sln-ims": ("Ims", "Solution", "ims"),
    "sln-ems": ("Ems", "Solution", "ems"),
    "sln-pts": ("Pts", "Solution", "pts"),
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
        f = Field(name="x", type=ftype, block="options", shape=shape, optional=optional)
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
        f = Field(name="x", type=ftype, block="period", shape=shape, optional=False)
        result = py_type(f)
        assert result.startswith("Optional["), (
            f"Expected Optional for period {ftype} array but got {result!r}"
        )

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
        f = Field(name="x", type=ftype, block="options", shape=shape)
        assert is_generatable(f) == generatable

    def test_is_generatable_file_record(self):
        """A record with a filein/fileout child is generatable as a path."""
        child_in = Field(name="filein", type="keyword", block="options")
        f = Field(
            name="my_filerecord",
            type="record",
            block="options",
            children={"filein": child_in},
        )
        assert is_generatable(f)

    def test_schema_class_empty_returns_empty_string(self):
        assert schema_class([], "_Empty") == ""

    def test_schema_class_basic_structure(self):
        schema = [
            {"name": "cellid", "role": "cellid", "dfn_type": "integer"},
            {"name": "head", "role": "value", "dfn_type": "double"},
        ]
        result = schema_class(schema, "_PeriodSchema")
        assert "    class _PeriodSchema(Schema):" in result
        assert 'Column("cellid"' in result
        assert 'role="cellid"' in result
        assert 'dfn_type="integer"' in result
        assert 'Column("head"' in result
        assert 'role="value"' in result

    def test_schema_class_column_name_alignment(self):
        schema = [
            {"name": "ab", "role": "value", "dfn_type": "double"},
            {"name": "abcdef", "role": "cellid", "dfn_type": "integer"},
        ]
        result = schema_class(schema, "_Schema")
        col_lines = [ln for ln in result.splitlines() if "= Column(" in ln]
        assert len(col_lines) == 2
        # The '= Column(' should start at the same position in both lines.
        positions = [ln.index("= Column(") for ln in col_lines]
        assert positions[0] == positions[1]

    def test_schema_class_long_line_wraps(self):
        # A column with many optional args whose single-line form exceeds 100 chars.
        schema = [
            {
                "name": "very_long_column_name_xyz",
                "role": "value",
                "dfn_type": "double",
                "time_series": True,
                "dtype": "np.object_",
                "shape": "(ncelldim)",
            },
        ]
        result = schema_class(schema, "_Schema")
        for line in result.splitlines():
            assert len(line) <= 100, f"Line exceeds 100 chars: {line!r}"

    def test_schema_class_optional_args_emitted(self):
        schema = [
            {
                "name": "col",
                "role": "value",
                "dfn_type": "double",
                "optional": True,
                "time_series": True,
                "dtype": "np.float64",
                "prefix": "pfx",
                "shape": "(n)",
            },
        ]
        result = schema_class(schema, "_Schema")
        assert "optional=True" in result
        assert "time_series=True" in result
        assert 'dtype="np.float64"' in result
        assert 'prefix="pfx"' in result
        assert 'shape="(n)"' in result


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
        assert "attrs" in all_imports
        assert "Package" in all_imports

    def test_outpath(self, dfn_name, expected_class, expected_base, all_dfns):
        root = Path("/fake/mf6")
        dfn = self._get_dfn(dfn_name, all_dfns)
        spec = build_component_spec(dfn, root=root)
        assert spec.outpath == root / "gwf" / f"{expected_class.lower()}.py"


# Layer 2: Solution-tier ComponentSpec tests
@pytest.mark.parametrize(
    "dfn_name,expected_class,expected_base,expected_slntype",
    [(k, v[0], v[1], v[2]) for k, v in SOLUTION_TIER.items()],
)
class TestSolutionTierComponentSpec:
    """Verify build_component_spec() for each solution-tier DFN."""

    def _get_dfn(self, dfn_name, all_dfns):
        if dfn_name not in all_dfns:
            pytest.skip(f"{dfn_name} not available in DFN set")
        return all_dfns[dfn_name]

    def test_class_name(self, dfn_name, expected_class, expected_base, expected_slntype, all_dfns):
        dfn = self._get_dfn(dfn_name, all_dfns)
        spec = build_component_spec(dfn, root=Path("/fake"))
        assert spec.class_name == expected_class

    def test_base_class(self, dfn_name, expected_class, expected_base, expected_slntype, all_dfns):
        dfn = self._get_dfn(dfn_name, all_dfns)
        spec = build_component_spec(dfn, root=Path("/fake"))
        assert spec.base_class == expected_base

    def test_slntype(self, dfn_name, expected_class, expected_base, expected_slntype, all_dfns):
        dfn = self._get_dfn(dfn_name, all_dfns)
        spec = build_component_spec(dfn, root=Path("/fake"))
        assert spec.slntype == expected_slntype

    def test_outpath(self, dfn_name, expected_class, expected_base, expected_slntype, all_dfns):
        root = Path("/fake/mf6")
        dfn = self._get_dfn(dfn_name, all_dfns)
        spec = build_component_spec(dfn, root=root)
        assert spec.outpath == root / f"{expected_class.lower()}.py"

    def test_imports_include_solution(
        self, dfn_name, expected_class, expected_base, expected_slntype, all_dfns
    ):
        dfn = self._get_dfn(dfn_name, all_dfns)
        spec = build_component_spec(dfn, root=Path("/fake"))
        all_imports = "\n".join(
            spec.imports.get("stdlib", [])
            + spec.imports.get("third_party", [])
            + spec.imports.get("flopy4", [])
        )
        assert "attrs" in all_imports
        assert "Solution" in all_imports
        assert "ClassVar" in all_imports


# Layer 2b: List-field expansion
def test_lak_numeric_index_autodetects_cellid(all_dfns, dfn_path):
    """LAK packagedata/connectiondata are emitted as recarray fields with schemas."""
    if "gwf-lak" not in all_dfns:
        pytest.skip("gwf-lak not in DFN set")
    v1_dfns = Dfn.load_all(dfn_path, schema_version="2.0.0.dev1")
    spec = build_component_spec(
        all_dfns["gwf-lak"], root=Path("/fake"), v1_dfn=v1_dfns.get("gwf-lak")
    )
    field_map = {f.py_name: f for f in spec.fields}

    # New codegen: block schemas exist for list blocks (single recarray field each)
    assert "packagedata" in spec.block_schemas
    assert "connectiondata" in spec.block_schemas
    assert "packagedata" in field_map
    assert "connectiondata" in field_map
    # Schemas contain feature_id roles (advanced package, no spatial cellid in packagedata)
    pd_schema = spec.block_schemas["packagedata"]
    assert any(col.get("role") == "feature_id" for col in pd_schema)


def test_mvr_list_fields_expanded_and_optional(all_dfns):
    """gwf-mvr period data is emitted as a single stress_period_data recarray field."""
    if "gwf-mvr" not in all_dfns:
        pytest.skip("gwf-mvr not in DFN set")
    spec = build_component_spec(all_dfns["gwf-mvr"], root=Path("/fake"))
    field_map = {f.py_name: f for f in spec.fields}

    # New codegen: period data → single _stress_period_data field with period schema
    assert spec.period_schema, "MVR should have a period_schema"
    assert "_stress_period_data" in field_map
    spd_field = field_map["_stress_period_data"]
    assert spd_field.type_annotation == "Optional[dict[int, np.recarray]]"
    # Packages block → single recarray field
    assert "packages" in field_map or "packages" in spec.block_schemas


# Layer 2d: BlockPropertySpec (Phase 2)
class TestBlockPropertySpec:
    """Verify BlockPropertySpec population in build_component_spec."""

    @pytest.fixture
    def lak_spec(self, all_dfns, dfn_path):
        if "gwf-lak" not in all_dfns:
            pytest.skip("gwf-lak not in DFN set")
        v1_dfns = Dfn.load_all(dfn_path, schema_version="2.0.0.dev1")
        return build_component_spec(
            all_dfns["gwf-lak"], root=Path("/fake"), v1_dfn=v1_dfns.get("gwf-lak")
        )

    def test_lak_block_count(self, lak_spec):
        assert len(lak_spec.block_properties) == 4

    def test_lak_block_names(self, lak_spec):
        names = [bp.block_name for bp in lak_spec.block_properties]
        assert set(names) == {"packagedata", "connectiondata", "tables", "outlets"}

    def test_lak_packagedata_dim_declared(self, lak_spec):
        bp = next(b for b in lak_spec.block_properties if b.block_name == "packagedata")
        assert bp.dim_attr == "nlakes"
        assert bp.dim_is_dfn_declared is True

    def test_lak_connectiondata_dim_synthetic(self, lak_spec):
        bp = next(b for b in lak_spec.block_properties if b.block_name == "connectiondata")
        assert bp.dim_attr == "nconnectiondata"
        assert bp.dim_is_dfn_declared is False

    def test_lak_tables_dim_declared(self, lak_spec):
        bp = next(b for b in lak_spec.block_properties if b.block_name == "tables")
        assert bp.dim_attr == "ntables"
        assert bp.dim_is_dfn_declared is True

    def test_lak_outlets_dim_declared(self, lak_spec):
        bp = next(b for b in lak_spec.block_properties if b.block_name == "outlets")
        assert bp.dim_attr == "noutlets"
        assert bp.dim_is_dfn_declared is True

    def test_lak_ifno_collision_prefixed(self, lak_spec):
        # ifno appears in packagedata, connectiondata, and tables — all get block-prefixed attrs
        for block in ("packagedata", "connectiondata", "tables"):
            bp = next(b for b in lak_spec.block_properties if b.block_name == block)
            assert bp.attr_name_map.get("ifno") == f"{block}_ifno", (
                f"ifno in {block} should be prefixed as {block}_ifno"
            )

    def test_lak_outlets_period_collision_prefixed(self, lak_spec):
        # invert/width/slope/rough appear as both outlets packagedata columns and
        # period field keywords — static columns must take outlets_ prefix so period
        # fields can always use the bare keyword name.
        bp = next(b for b in lak_spec.block_properties if b.block_name == "outlets")
        for col_name in ("invert", "width", "slope", "rough"):
            assert bp.attr_name_map.get(col_name) == f"outlets_{col_name}", (
                f"outlets.{col_name} should be prefixed as outlets_{col_name} "
                "(collides with period field keyword)"
            )
        # outletno, lakein, lakeout, couttype are not period field names — bare names
        for col_name in ("outletno", "lakein", "lakeout", "couttype"):
            assert bp.attr_name_map.get(col_name) == col_name, (
                f"outlets.{col_name} should use bare name (no period field conflict)"
            )

    def test_lak_connectiondata_cellid(self, lak_spec):
        bp = next(b for b in lak_spec.block_properties if b.block_name == "connectiondata")
        cellid_col = next((c for c in bp.columns if c.name == "cellid"), None)
        assert cellid_col is not None
        assert cellid_col.is_cellid is True

    def test_lak_tables_prefix_columns_excluded(self, lak_spec):
        bp = next(b for b in lak_spec.block_properties if b.block_name == "tables")
        # tab6 and filein are prefix tokens — excluded from attr_name_map
        assert "tab6" not in bp.attr_name_map
        assert "filein" not in bp.attr_name_map

    def test_no_block_properties_without_v1(self, all_dfns):
        if "gwf-lak" not in all_dfns:
            pytest.skip("gwf-lak not in DFN set")
        spec = build_component_spec(all_dfns["gwf-lak"], root=Path("/fake"))
        assert spec.block_properties == []


# Layer 2c: Compound record expansion
def test_can_expand_record_all_keywords(all_dfns):
    """A record whose children are all keyword type (like cvoptions) is expandable."""
    if "gwf-npf" not in all_dfns:
        pytest.skip("gwf-npf not in DFN set")
    cvoptions = all_dfns["gwf-npf"]["blocks"]["options"]["cvoptions"]
    assert can_expand_record(cvoptions)


def test_can_expand_record_with_positional_required_data(all_dfns):
    """A record with required scalar+keyword children (rewet_record) generates an inner class."""
    if "gwf-npf" not in all_dfns:
        pytest.skip("gwf-npf not in DFN set")
    from flopy4.mf6.utils.codegen.filters import can_generate_record_class

    rewet_record = all_dfns["gwf-npf"]["blocks"]["options"]["rewet_record"]
    assert not can_expand_record(rewet_record)
    assert can_generate_record_class(rewet_record)


def test_rcloserecord_generates_inner_class(all_dfns):
    """rcloserecord has a tagged scalar first child (not keyword): generates an inner class."""
    if "sln-ims" not in all_dfns:
        pytest.skip("sln-ims not in DFN set")
    from flopy4.mf6.utils.codegen.filters import can_generate_record_class

    rcloserecord = all_dfns["sln-ims"]["blocks"]["linear"]["rcloserecord"]
    assert can_generate_record_class(rcloserecord)


def test_ims_compound_records_expanded(all_dfns):
    """sln-ims: rcloserecord and no_ptcrecord both become inner classes."""
    if "sln-ims" not in all_dfns:
        pytest.skip("sln-ims not in DFN set")
    spec = build_component_spec(all_dfns["sln-ims"], root=Path("/fake"))
    field_map = {f.py_name: f for f in spec.fields}

    # rcloserecord dfn → rclose field (record suffix stripped), Rclose inner class
    assert "rclose" in field_map, "rclose should generate as inner class parent field"
    assert field_map["rclose"].generatable
    assert field_map["rclose"].type_annotation == "Optional[Rclose]"
    assert any(r.class_name == "Rclose" for r in spec.inner_classes)

    # inner_rclose is now inside Rclose, not a standalone flat field
    assert "inner_rclose" not in field_map, "inner_rclose should not be a standalone field"

    # no_ptcrecord dfn → no_ptc field (record suffix stripped), NoPtc inner class
    assert "no_ptc" in field_map, "no_ptc should generate as inner class parent field"
    assert field_map["no_ptc"].generatable
    assert field_map["no_ptc"].type_annotation == "Optional[NoPtc]"
    assert any(r.class_name == "NoPtc" for r in spec.inner_classes)

    # no partial TODOs for either record
    todo_names = {f.dfn_name for f in spec.fields if not f.generatable}
    assert "rcloserecord" not in todo_names
    assert "no_ptcrecord" not in todo_names


def test_npf_compound_records_expanded(all_dfns):
    """gwf-npf: cvoptions/xt3doptions/rewet_record all become inner classes."""
    if "gwf-npf" not in all_dfns:
        pytest.skip("gwf-npf not in DFN set")
    spec = build_component_spec(all_dfns["gwf-npf"], root=Path("/fake"))
    field_map = {f.py_name: f for f in spec.fields}
    class_names = {r.class_name for r in spec.inner_classes}

    # cvoptions (variablecv + dewatered) → inner class, not flat bools
    assert "cvoptions" in field_map and field_map["cvoptions"].generatable
    assert field_map["cvoptions"].type_annotation == "Optional[Cvoptions]"
    assert "Cvoptions" in class_names
    assert "variablecv" not in field_map
    assert "dewatered" not in field_map

    # xt3doptions (xt3d + rhs) → inner class, not flat bools
    assert "xt3doptions" in field_map and field_map["xt3doptions"].generatable
    assert field_map["xt3doptions"].type_annotation == "Optional[Xt3doptions]"
    assert "Xt3doptions" in class_names
    assert "xt3d" not in field_map
    assert "rhs" not in field_map

    # rewet_record dfn → rewet field (record suffix stripped), Rewet inner class
    assert "rewet" in field_map and field_map["rewet"].generatable
    assert field_map["rewet"].type_annotation == "Optional[Rewet]"
    assert "Rewet" in class_names

    # No TODOs in NPF options now
    todo_names = {f.dfn_name for f in spec.fields if not f.generatable}
    assert "rewet_record" not in todo_names


# Layer 3: End-to-end generation
def test_simple_tier_generates_importable_files(dfn_path, tmp_path, all_dfns):
    """Run make_all() and verify each simple-tier file is importable with the right class."""
    (tmp_path / "gwf").mkdir()

    skip = {n for n in all_dfns if n not in SIMPLE_TIER}
    specs = make_modules(dfndir=dfn_path, outdir=tmp_path, skip=skip)

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


def test_solution_tier_generates_importable_files(dfn_path, tmp_path, all_dfns):
    """Run make_all() and verify each solution-tier file is importable with Solution base."""
    from flopy4.mf6.solution import Solution

    skip = {n for n in all_dfns if n not in SOLUTION_TIER}
    specs = make_modules(dfndir=dfn_path, outdir=tmp_path, skip=skip)

    generated = {s.dfn_name: s for s in specs}

    for dfn_name, (expected_class, _, expected_slntype) in SOLUTION_TIER.items():
        if dfn_name not in all_dfns:
            continue
        if dfn_name not in generated:
            pytest.fail(f"{dfn_name} was expected but not generated")

        spec = generated[dfn_name]
        assert spec.outpath.exists(), f"Missing {spec.outpath}"

        mod_name = f"_codegen_test_sln.{expected_class.lower()}"
        mod_spec = importlib.util.spec_from_file_location(mod_name, spec.outpath)
        mod = importlib.util.module_from_spec(mod_spec)

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
        cls = getattr(mod, expected_class)
        assert issubclass(cls, Solution), f"{expected_class} should subclass Solution"
        assert cls.slntype == expected_slntype, (
            f"{expected_class}.slntype expected {expected_slntype!r}, got {cls.slntype!r}"
        )


def _load_class_from_spec(spec, mod_name: str, expected_class: str):
    """Generate, load, and return the class from a ComponentSpec. Cleans up module state."""
    mod_spec = importlib.util.spec_from_file_location(mod_name, spec.outpath)
    assert mod_spec is not None and mod_spec.loader is not None
    mod = importlib.util.module_from_spec(mod_spec)
    components_snapshot = dict(COMPONENTS)
    sys_modules_keys = set(sys.modules)
    try:
        mod_spec.loader.exec_module(mod)  # type: ignore[union-attr]
        assert hasattr(mod, expected_class), f"Class {expected_class} not found in {spec.outpath}"
        return getattr(mod, expected_class)
    finally:
        COMPONENTS.clear()
        COMPONENTS.update(components_snapshot)
        for key in set(sys.modules) - sys_modules_keys:
            del sys.modules[key]


def test_transport_tier_generates_importable_files(dfn_path, tmp_path, all_dfns):
    """gwt-disv, gwt-ist, gwe-disv generate importable Package subclasses."""
    for subdir in ("gwt", "gwe"):
        (tmp_path / subdir).mkdir()

    target = {n for n in TRANSPORT_TIER if n in all_dfns}
    skip = {n for n in all_dfns if n not in target}
    specs = make_modules(dfndir=dfn_path, outdir=tmp_path, skip=skip)
    generated = {s.dfn_name: s for s in specs}

    from flopy4.mf6.package import Package

    for dfn_name, (expected_class, _, subdir) in TRANSPORT_TIER.items():
        if dfn_name not in all_dfns:
            continue
        assert dfn_name in generated, f"{dfn_name} was not generated"
        spec = generated[dfn_name]
        assert spec.outpath == tmp_path / subdir / f"{expected_class.lower()}.py"
        cls = _load_class_from_spec(spec, f"_codegen_test_transport.{dfn_name}", expected_class)
        assert issubclass(cls, Package)


def test_oc_tier_generates_importable_files(dfn_path, tmp_path, all_dfns):
    """gwt-oc, gwe-oc, prt-oc generate importable Package subclasses with OC period fields."""
    for subdir in ("gwt", "gwe", "prt"):
        (tmp_path / subdir).mkdir()

    target = {n for n in OC_TIER if n in all_dfns}
    skip = {n for n in all_dfns if n not in target}
    specs = make_modules(dfndir=dfn_path, outdir=tmp_path, skip=skip)
    generated = {s.dfn_name: s for s in specs}

    from flopy4.mf6.package import Package

    for dfn_name, (expected_class, _, subdir) in OC_TIER.items():
        if dfn_name not in all_dfns:
            continue
        assert dfn_name in generated, f"{dfn_name} was not generated"
        spec = generated[dfn_name]
        assert spec.outpath == tmp_path / subdir / f"{expected_class.lower()}.py"
        cls = _load_class_from_spec(spec, f"_codegen_test_oc.{dfn_name}", expected_class)
        assert issubclass(cls, Package)
        # Verify at least one OC period field was generated
        oc_fields = [f for f in spec.fields if f.py_name.startswith(("save_", "print_"))]
        assert oc_fields, f"{dfn_name} should have save_/print_ period fields"


def test_utl_tier_generates_importable_files(dfn_path, tmp_path, all_dfns):
    """utl-* packages generate importable Package subclasses (including utl-tas inner classes)."""
    (tmp_path / "utl").mkdir()

    target = {n for n in UTL_TIER if n in all_dfns}
    skip = {n for n in all_dfns if n not in target}
    specs = make_modules(dfndir=dfn_path, outdir=tmp_path, makedirs=True, skip=skip)
    generated = {s.dfn_name: s for s in specs}

    from flopy4.mf6.package import Package

    for dfn_name, (expected_class, _) in UTL_TIER.items():
        if dfn_name not in all_dfns:
            continue
        assert dfn_name in generated, f"{dfn_name} was not generated"
        spec = generated[dfn_name]
        assert spec.outpath == tmp_path / "utl" / f"{expected_class.lower()}.py"
        cls = _load_class_from_spec(spec, f"_codegen_test_utl.{dfn_name}", expected_class)
        assert issubclass(cls, Package)


def test_exg_tier_generates_importable_files(dfn_path, tmp_path, all_dfns):
    """exg-* packages generate importable Package subclasses (including 0-field pass-only)."""
    (tmp_path / "exg").mkdir()

    target = {n for n in EXG_TIER if n in all_dfns}
    skip = {n for n in all_dfns if n not in target}
    specs = make_modules(dfndir=dfn_path, outdir=tmp_path, makedirs=True, skip=skip)
    generated = {s.dfn_name: s for s in specs}

    from flopy4.mf6.package import Package

    for dfn_name, (expected_class, _) in EXG_TIER.items():
        if dfn_name not in all_dfns:
            continue
        assert dfn_name in generated, f"{dfn_name} was not generated"
        spec = generated[dfn_name]
        assert spec.outpath == tmp_path / "exg" / f"{expected_class.lower()}.py"
        cls = _load_class_from_spec(spec, f"_codegen_test_exg.{dfn_name}", expected_class)
        assert issubclass(cls, Package)
