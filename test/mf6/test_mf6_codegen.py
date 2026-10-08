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

import importlib
import importlib.util
import sys
import warnings
from pathlib import Path

import attrs
import numpy as np
import pytest
from modflow_devtools.dfns.schema import Array, Double, Integer, Keyword, Record, String

from flopy4.mf6.component import FNAMES
from flopy4.mf6.utils.codegen.filters import (
    array_column,
    attr_column,
    can_expand_record,
    class_name,
    feature_id_column,
    is_generatable,
    item_class,
    model_abbr,
    module_name,
    output_path,
    py_type,
    safe_name,
    value_column,
)
from flopy4.mf6.utils.codegen.make import build_component_spec, check_mixins, make_modules


# Shared fixtures
@pytest.fixture(scope="session")
def all_dfns(dfn_path):
    """Load all DFNs as a flat {name: Component} dict."""
    from modflow_devtools.dfns import LocalDfnRegistry

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*modflow_devtools.dfns.*experimental.*")
        registry = LocalDfnRegistry(path=dfn_path)
        return registry.spec(schema_version="2.0.0.dev3").components


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
    "gwf-csub": ("Csub", "Package"),
    "gwf-maw": ("Maw", "Package"),
    "gwf-uzf": ("Uzf", "Package"),
    "gwf-hfb": ("Hfb", "Package"),
    "gwf-sfr": ("Sfr", "Package"),
}

# Transport model packages: gwt-ist (immobile storage transport, multi=True).
TRANSPORT_TIER = {
    "gwt-ist": ("Ist", "Package", "gwt"),
}

# Tier 1a: OC period keystring union — saverecord/printrecord arms become
# real typed Save/Print classes composed into stress_period_data, the same
# generic mechanism LAK/SFR/MAW use for their own period keystring settings.
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
    "utl-ts": ("Ts", "Package"),
}

# Exchange packages (exg/) for the model types flopy4 has classes for.
EXG_TIER = {
    "exg-gwegwe": ("Gwegwe", "Exchange"),
    "exg-gwfgwe": ("Gwfgwe", "Exchange"),
    "exg-gwfgwf": ("Gwfgwf", "Exchange"),
    "exg-gwfgwt": ("Gwfgwt", "Exchange"),
    "exg-gwfprt": ("Gwfprt", "Exchange"),
    "exg-gwtgwt": ("Gwtgwt", "Exchange"),
}

SOLUTION_TIER = {
    "sln-ims": ("Ims", "Solution", "ims"),
    "sln-ems": ("Ems", "Solution", "ems"),
    "sln-pts": ("Pts", "Solution", "pts"),
}


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
            ("gwf-nam", "Gwf"),
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
            ("gwf-nam", "gwf/__init__.py"),
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
        "field, block_name, expected",
        [
            (Keyword(name="x"), "options", "bool"),
            (Keyword(name="x", optional=True), "options", "bool"),  # keywords never Optional
            (Integer(name="x"), "options", "int"),
            (Integer(name="x", optional=True), "options", "Optional[int]"),
            (Double(name="x"), "options", "float"),
            (String(name="x"), "options", "str"),
            (Array(name="x", dtype="double", shape=["nodes"]), "options", "FloatArrayLike"),
            (
                Array(name="x", dtype="integer", shape=["nodes"], optional=True),
                "options",
                "Optional[IntArrayLike]",
            ),
            (
                Array(name="x", dtype="keyword", shape=["nper"], optional=True),
                "options",
                "Optional[NDArray[np.bool_]]",
            ),
        ],
    )
    def test_py_type(self, field, block_name, expected):
        assert py_type(field, block_name) == expected

    @pytest.mark.parametrize(
        "field, generatable",
        [
            (Keyword(name="x"), True),
            (Array(name="x", dtype="double", shape=["nodes"]), True),
            (Integer(name="x"), True),
            (String(name="x"), True),
            (Record(name="x", fields={"a": Integer(name="a"), "b": Integer(name="b")}), False),
        ],
    )
    def test_is_generatable(self, field, generatable):
        assert is_generatable(field) == generatable

    def test_is_generatable_file_record(self):
        """A record with a filein/fileout child is generatable as a path."""
        from modflow_devtools.dfns.schema import File

        f = Record(
            name="my_filerecord",
            fields={
                "filein": Keyword(name="filein"),
                "my_filename": File(name="my_filename", direction="in"),
            },
        )
        assert is_generatable(f)

    def test_item_class_empty_returns_empty_string(self):
        assert item_class([], "StressPeriodData") == ""

    def test_item_class_static_block_no_aux(self):
        # No sized column in the schema, no aux field. Real field()
        # metadata (pk=/etc.) is the schema.
        schema = [
            feature_id_column("ifno", pk=True),
            value_column("strt"),
            attr_column("boundname", "str", {}, optional=True),
        ]
        result = item_class(schema, "Packagedata")
        assert "@attrs.define" in result
        assert "class Packagedata(Item):" in result
        assert "ifno: int = field(index=True, pk=True)" in result
        assert "strt: float" in result
        assert "boundname: Optional[str] = field(default=None, optional=True)" in result
        assert "aux" not in result

    def test_item_class_feature_id_with_fk_uses_fk_metadata(self):
        # A feature_id column always carries index= (it needs MF6's 0-based/
        # 1-based conversion); one with a real fk target also carries fk=,
        # not pk= (pk and fk are mutually exclusive relational roles).
        schema = [
            feature_id_column("ifno", fk="packagedata.ifno"),
            feature_id_column("iconn", pk=True),
        ]
        result = item_class(schema, "Connectiondata")
        assert 'ifno: int = field(index=True, fk="packagedata.ifno")' in result
        assert "iconn: int = field(index=True, pk=True)" in result

    def test_item_class_sized_column(self):
        # A column sized by a package field (aux by auxiliary) is a tuple
        # with that shape, in DFN order before boundname.
        schema = [
            attr_column("cellid", "tuple", {"cellid": True}, optional=False),
            value_column("head"),
            array_column("aux", "auxiliary", optional=True),
            attr_column("boundname", "str", {}, optional=True),
        ]
        result = item_class(schema, "StressPeriodData")
        assert (
            'aux: tuple[float, ...] = field(default=(), array=True, shape=("auxiliary",), '
            "optional=True)" in result
        )
        assert result.index("aux:") < result.index("boundname:")

    def test_item_class_field_order_matches_schema(self):
        # Required fields declared in schema order, then optional.
        schema = [
            feature_id_column("ifno"),
            value_column("strt"),
            value_column("nlakeconn", "integer"),
            attr_column("boundname", "str", {}, optional=True),
        ]
        result = item_class(schema, "Packagedata")
        lines = [ln.strip() for ln in result.splitlines() if ":" in ln and "class" not in ln]
        names = [ln.split(":")[0] for ln in lines]
        assert names == ["ifno", "strt", "nlakeconn", "boundname"]

    def test_item_class_inline_keyword_optional(self):
        # keyword column -> Optional[str], tagged=True (same convention
        # record.py's Record uses for optional keyword tokens).
        schema = [
            value_column("pname", "string", object_dtype=True),
            attr_column("mixed", "str", {"tagged": True}, optional=True),
        ]
        result = item_class(schema, "Fileinput")
        assert "mixed: Optional[str] = field(default=None, tagged=True, optional=True)" in result

    def test_item_class_cellid_metadata(self):
        schema = [attr_column("cellid", "tuple", {"cellid": True}, optional=False)]
        result = item_class(schema, "StressPeriodData")
        assert "cellid: tuple = field(cellid=True)" in result

    def test_item_class_time_series_metadata(self):
        schema = [
            value_column("head", time_series=True),
        ]
        result = item_class(schema, "StressPeriodData")
        assert "head: Union[float, str] = field(time_series=True)" in result


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


def test_simulation_spec(all_dfns):
    root = Path("/fake/mf6")
    spec = build_component_spec(all_dfns["sim-nam"], root=root, dfns=all_dfns)
    assert spec.class_name == "Simulation"
    assert spec.base_class == "Context"
    assert spec.mixins == ["SimulationMethods"]
    assert spec.outpath == root / "simulation.py"
    types = {f.py_name: f.type_annotation for f in spec.fields}
    # binding lists become typed child fields
    assert types["tdis"] == "Tdis"
    assert types["models"] == "dict[str, Model]"
    assert types["exchanges"] == "dict[str, Exchange]"
    assert types["solutiongroup"] == "dict[str, Solution]"
    assert not spec.item_classes
    assert {"continue_", "nocheck", "maxerrors", "mxiter"} <= set(types)


def test_model_spec(all_dfns):
    root = Path("/fake/mf6")
    spec = build_component_spec(all_dfns["gwt-nam"], root=root, dfns=all_dfns)
    assert spec.class_name == "Gwt"
    assert spec.base_class == "Model"
    assert spec.mixins == ["ModelMethods"]
    assert spec.outpath == root / "gwt" / "__init__.py"
    types = {f.py_name: f.type_annotation for f in spec.fields}
    # one discretization, first; repeating packages are lists
    assert next(iter(types)) == "list_"
    packages = [f.py_name for f in spec.fields if f.spec_call.startswith("child(")]
    assert packages[0] == "dis"
    assert types["dis"] == "Optional[Union[Dis, Disu, Disv]]"
    assert types["fmi"] == "Optional[Fmi]"
    assert types["ist"] == "list[Ist]"
    assert types["api"] == "list[Api]"
    # packages without a class yet are left out
    assert not {"mwt", "sft", "uzt"} & set(types)
    assert "netcdf_input_file" in types
    assert "packages" not in types
    assert spec.exports[0] == "Gwt"
    assert {"Dis", "Disu", "Disv", "Fmi", "Ist"} <= set(spec.exports)


def test_model_spec_shares_variant_field(all_dfns):
    spec = build_component_spec(all_dfns["gwf-nam"], root=Path("/fake"), dfns=all_dfns)
    types = {f.py_name: f.type_annotation for f in spec.fields}
    assert types["chd"] == "list[Union[Chd, Chdg]]"
    assert types["rch"] == "list[Union[Rch, Rcha]]"
    assert types["csub"] == "Optional[Csub]"
    assert types["newtonoptions"] == "Optional[Newtonoptions]"
    calls = {f.py_name: f.spec_call for f in spec.fields}
    assert "converter=Newtonoptions.from_flag" in calls["newtonoptions"]
    # NPF's other records have required members
    npf = build_component_spec(all_dfns["gwf-npf"], root=Path("/fake"), dfns=all_dfns)
    flags = {f.py_name for f in npf.fields if ".from_flag" in f.spec_call}
    assert flags == {"xt3doptions", "cvoptions"}
    assert spec.mixins == ["GwfMethods", "ModelMethods"]


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
def test_lak_numeric_index_autodetects_cellid(all_dfns):
    """LAK packagedata/connectiondata are emitted as recarray fields with schemas."""
    if "gwf-lak" not in all_dfns:
        pytest.skip("gwf-lak not in DFN set")
    spec = build_component_spec(all_dfns["gwf-lak"], root=Path("/fake"))
    field_map = {f.py_name: f for f in spec.fields}

    # Item classes exist for list blocks (single list field each)
    item_classes = {ic.class_name: ic for ic in spec.item_classes}
    assert "Packagedata" in item_classes
    assert "Connectiondata" in item_classes
    assert "packagedata" in field_map
    assert "connectiondata" in field_map
    # Schemas contain feature ids (advanced package, no spatial cellid in packagedata)
    pd_schema = item_classes["Packagedata"].schema
    assert any("index=True" in col.rhs for col in pd_schema)


@pytest.mark.parametrize(
    "name,item,expected",
    [
        ("exg-gwfgwf", "Exchangedata", {"cellidm1": "1", "cellidm2": "2"}),
        ("exg-gwtgwt", "Exchangedata", {"cellidm1": "1", "cellidm2": "2"}),
        ("gwf-gnc", "Gncdata", {"cellidn": "1", "cellidm": "2", "cellidsj": "1"}),
        ("gwf-chd", "StressPeriodData", {"cellid": True}),
    ],
)
def test_cellid_model_from_dfn(all_dfns, name, item, expected):
    """Each cellid column says which model's grid it refers to, as the
    DFN does: "1"/"2" for an exchange's first/second model, True for the
    component's own."""
    if name not in all_dfns:
        pytest.skip(f"{name} not in DFN set")
    spec = build_component_spec(all_dfns[name], root=Path("/fake"))
    schema = {ic.class_name: ic for ic in spec.item_classes}[item].schema
    rhs = {col.name: col.rhs for col in schema}
    for column, model in expected.items():
        assert f"cellid={model!r}".replace("'", '"') in rhs[column]


def test_mvr_list_fields_expanded_and_optional(all_dfns):
    """gwf-mvr period data is emitted as a single stress_period_data recarray field."""
    if "gwf-mvr" not in all_dfns:
        pytest.skip("gwf-mvr not in DFN set")
    spec = build_component_spec(all_dfns["gwf-mvr"], root=Path("/fake"))
    field_map = {f.py_name: f for f in spec.fields}

    # Period data -> single _stress_period_data field with a period item class
    assert "StressPeriodData" in {ic.class_name for ic in spec.item_classes}
    assert "_stress_period_data" in field_map
    spd_field = field_map["_stress_period_data"]
    assert spd_field.type_annotation == "Optional[dict[int, list[StressPeriodData]]]"
    # Packages block → single list field
    assert "packages" in field_map


# Layer 2d: BlockPropertySpec (Phase 2)
class TestBlockPropertySpec:
    """Verify BlockPropertySpec population in build_component_spec."""

    @pytest.fixture
    def lak_spec(self, all_dfns):
        if "gwf-lak" not in all_dfns:
            pytest.skip("gwf-lak not in DFN set")
        return build_component_spec(all_dfns["gwf-lak"], root=Path("/fake"))

    def test_lak_block_count(self, lak_spec):
        assert len(lak_spec.block_properties) == 4

    def test_lak_block_names(self, lak_spec):
        # options holds a tagged list (ts_filerecord), which isn't a table
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


# Layer 2c: Compound record expansion
def test_can_expand_record_all_keywords(all_dfns):
    """A record whose children are all keyword type (like cvoptions) is expandable."""
    if "gwf-npf" not in all_dfns:
        pytest.skip("gwf-npf not in DFN set")
    cvoptions = all_dfns["gwf-npf"].blocks["options"].fields["cvoptions"]
    assert can_expand_record(cvoptions)


def test_can_expand_record_with_positional_required_data(all_dfns):
    """A record with required scalar+keyword children (rewet_record) generates an inner class."""
    if "gwf-npf" not in all_dfns:
        pytest.skip("gwf-npf not in DFN set")
    from flopy4.mf6.utils.codegen.filters import can_generate_record_class

    rewet_record = all_dfns["gwf-npf"].blocks["options"].fields["rewet_record"]
    assert not can_expand_record(rewet_record)
    assert can_generate_record_class(rewet_record)


def test_rcloserecord_generates_inner_class(all_dfns):
    """rcloserecord has a tagged scalar first child (not keyword): generates an inner class."""
    if "sln-ims" not in all_dfns:
        pytest.skip("sln-ims not in DFN set")
    from flopy4.mf6.utils.codegen.filters import can_generate_record_class

    rcloserecord = all_dfns["sln-ims"].blocks["linear"].fields["rcloserecord"]
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

    # no leading keyword: the first child's tag (INNER_RCLOSE) is the trigger
    rclose = next(r for r in spec.inner_classes if r.class_name == "Rclose")
    assert rclose.keyword == "inner_rclose"
    assert not next(f for f in rclose.fields if f.py_name == "inner_rclose").tagged

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
def test_simple_tier_generates_importable_files(tmp_path, all_dfns):
    """Run make_all() and verify each simple-tier file is importable with the right class."""
    (tmp_path / "gwf").mkdir()

    skip = {n for n in all_dfns if n not in SIMPLE_TIER}
    specs = make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip)

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
        components_snapshot = dict(FNAMES)
        sys_modules_keys = set(sys.modules)
        try:
            mod_spec.loader.exec_module(mod)
        finally:
            FNAMES.clear()
            FNAMES.update(components_snapshot)
            for key in set(sys.modules) - sys_modules_keys:
                del sys.modules[key]

        assert hasattr(mod, expected_class), f"Class {expected_class} not found in {spec.outpath}"


def test_solution_tier_generates_importable_files(tmp_path, all_dfns):
    """Run make_all() and verify each solution-tier file is importable with Solution base."""
    from flopy4.mf6.solution import Solution

    skip = {n for n in all_dfns if n not in SOLUTION_TIER}
    specs = make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip)

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

        components_snapshot = dict(FNAMES)
        sys_modules_keys = set(sys.modules)
        try:
            mod_spec.loader.exec_module(mod)
        finally:
            FNAMES.clear()
            FNAMES.update(components_snapshot)
            for key in set(sys.modules) - sys_modules_keys:
                del sys.modules[key]

        assert hasattr(mod, expected_class), f"Class {expected_class} not found in {spec.outpath}"
        cls = getattr(mod, expected_class)
        assert issubclass(cls, Solution), f"{expected_class} should subclass Solution"
        assert cls.slntype == expected_slntype, (
            f"{expected_class}.slntype expected {expected_slntype!r}, got {cls.slntype!r}"
        )


@pytest.mark.parametrize(
    "name,decl",
    [
        ("sim-tdis", "class Tdis(TdisMethods, Package):"),
        ("utl-ncf", "class Ncf(NcfMethods, Package):"),
        ("gwf-disv", "class Disv(DisvMethods, GridDimsMethods, Package):"),
        ("gwf-disu", "class Disu(DisuMethods, GridDimsMethods, Package):"),
        ("gwf-dis", "class Dis(DisMethods, GridDimsMethods, Package):"),
    ],
)
def test_mixins(tmp_path, all_dfns, name, decl):
    """Components listed in MIXINS get their method-only mixins as extra bases."""
    skip = {n for n in all_dfns if n != name}
    (spec,) = make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip, makedirs=True)
    assert spec.base_class == "Package"
    assert decl in spec.outpath.read_text()


@pytest.mark.parametrize(
    "name,shapes",
    [
        ("gwf-dis", {"delr": ("ncol",), "top": ("ncpl",), "botm": ("nodes",)}),
        ("gwf-disv", {"top": ("ncpl",), "botm": ("nodes",), "idomain": ("nodes",)}),
        ("olf-dis2d", {"bottom": ("ncpl",), "idomain": ("ncpl",)}),
    ],
)
def test_griddata_shapes_are_flat(all_dfns, name, shapes):
    """The grid packages' structured griddata shapes (Fortran order in the
    DFN) map to the derived dimension they span."""
    spec = build_component_spec(all_dfns[name], root=Path("/fake"))
    calls = {f.py_name: f.spec_call for f in spec.fields}
    for field_name, shape in shapes.items():
        assert f"shape={shape!r}".replace("'", '"') in calls[field_name]


def test_canonical_shape_rejects_unmatched():
    from flopy4.mf6.utils.codegen.filters import canonical_shape

    f = Array(name="x", dtype="double", shape=["nrow", "nlay"])
    with pytest.raises(ValueError, match="matches no derived dimension"):
        canonical_shape(f, {"ncpl": "nrow * ncol"})


@pytest.mark.parametrize(
    "name,derived",
    [
        ("gwf-dis", {"ncpl": "nrow * ncol", "nodes": "nlay * nrow * ncol", "ncelldim": "3"}),
        ("gwf-disv", {"nodes": "nlay * ncpl", "ncelldim": "2"}),
        ("gwf-disu", {"ncelldim": "1", "njas": "(nja - nodes) / 2"}),
        ("gwf-lak", {}),  # sum(packagedata.nlakeconn) isn't arithmetic
    ],
)
def test_derived_dims(all_dfns, name, derived):
    """Arithmetic DFN dimension expressions that aren't fields become
    DerivedDim descriptors."""
    assert build_component_spec(all_dfns[name], root=Path("/fake")).derived_dims == derived


def test_grid_package_dims(tmp_path, all_dfns):
    """Generated grid packages provide their dimensions and take griddata as
    lists, per-layer values, or structured arrays."""
    from flopy4.dimensions import DimensionProvider

    names = ("gwf-dis", "gwf-disv", "gwf-disu")
    skip = {n for n in all_dfns if n not in names}
    specs = {
        s.dfn_name: s
        for s in make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip, makedirs=True)
    }
    Dis = _load_class_from_spec(specs["gwf-dis"], "_codegen_test_grid.dis", "Dis")
    Disv = _load_class_from_spec(specs["gwf-disv"], "_codegen_test_grid.disv", "Disv")
    Disu = _load_class_from_spec(specs["gwf-disu"], "_codegen_test_grid.disu", "Disu")

    dis = Dis(
        nlay=2,
        nrow=3,
        ncol=4,
        delr=[1.0] * 4,
        top=np.full((3, 4), 10.0),
        botm=[5.0, 0.0],
        idomain=np.ones((2, 3, 4), dtype=np.int64),
    )
    assert isinstance(dis, DimensionProvider)
    assert dis.get_dims() == {
        "nlay": 2,
        "nrow": 3,
        "ncol": 4,
        "ncpl": 12,
        "nodes": 24,
        "ncelldim": 3,
    }
    assert isinstance(dis.delr, np.ndarray)
    assert dis.top.shape == (12,)
    assert dis.idomain.shape == (24,)
    np.testing.assert_array_equal(dis.botm, np.repeat([5.0, 0.0], 12))
    with pytest.raises(AttributeError, match="derived"):
        dis.nodes = 5

    disv = Disv(nlay=3, ncpl=5, nvert=8, top=1.0, botm=[0.0, -1.0, -2.0])
    assert disv.get_dims()["nodes"] == 15
    assert disv.botm.shape == (15,)

    assert Disu(nodes=4, nja=10).get_dims()["njas"] == 3


def test_subpackage_field(tmp_path, all_dfns):
    """A linked file record gets a typed child field; writing
    names the child's file in the record and writes the child at full
    precision."""
    from flopy4.mf6.utl.ncf import Ncf
    from flopy4.mf6.write_context import WriteContext

    skip = {n for n in all_dfns if n != "gwf-dis"}
    (spec,) = make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip, makedirs=True)
    text = spec.outpath.read_text()
    assert 'ncf: Optional[Ncf] = child(block="options", keyword="ncf6", direction="in")' in text
    assert "ncf_file" not in text
    Dis = _load_class_from_spec(spec, "_codegen_test_subpackage.dis", "Dis")

    lat = 35.123456789012345
    dis = Dis(nlay=1, nrow=1, ncol=1, delr=1.0, delc=1.0, top=1.0, botm=0.0)
    dis.filename = tmp_path / "gwf.dis"
    dis.ncf = Ncf(ncpl=1, latitude=[lat], longitude=[-120.0])
    dis.ncf.filename = tmp_path / "gwf.dis.ncf"
    dis.write(context=WriteContext(float_precision=4))

    assert "NCF6 FILEIN gwf.dis.ncf" in (tmp_path / "gwf.dis").read_text()
    assert repr(lat) in (tmp_path / "gwf.dis.ncf").read_text()


def test_check_mixins_rejects_unknown_component(all_dfns):
    check_mixins(all_dfns)
    with pytest.raises(ValueError, match="sim-tdis"):
        check_mixins({n: c for n, c in all_dfns.items() if n != "sim-tdis"})


@pytest.mark.parametrize(
    "selector,match",
    [("bogus", "matches no component"), ("model", "no component_ftype")],
)
def test_link_selector_errors(all_dfns, selector, match):
    sim = all_dfns["sim-nam"].model_copy(deep=True)
    sim.blocks["timing"].fields["tdis6"].component = selector
    with pytest.raises(ValueError, match=match):
        build_component_spec(sim, root=Path("/fake"), dfns=all_dfns)


@pytest.mark.parametrize(
    "name,field,cls",
    [
        ("sim-nam", "hpc", "Hpc"),
        ("sim-tdis", "ats", "Ats"),
        ("sim-nam", "tdis", "Tdis"),
        ("gwf-npf", "tvk", "Tvk"),
        ("gwf-sto", "tvs", "Tvs"),
        ("exg-gwfgwf", "mvr", "Mvr"),
        ("exg-gwfgwf", "gnc", "Gnc"),
        ("exg-gwtgwt", "mvt", "Mvt"),
        ("exg-gwegwe", "mve", "Mve"),
        ("gwf-wel", "obs", "Obs"),
        ("gwf-lak", "obs", "Obs"),
        ("exg-gwfgwf", "obs", "Obs"),
    ],
)
def test_dfn_link_is_child(tmp_path, all_dfns, name, field, cls):
    """A DFN file link to a component with a class is a child field."""
    skip = {n for n in all_dfns if n != name}
    (spec,) = make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip, makedirs=True)
    text = "".join(spec.outpath.read_text().split())
    assert f"{field}:Optional[{cls}]=child(" in text or f"{field}:{cls}=child(" in text


@pytest.mark.parametrize(
    "name,column",
    [
        ("gwf-lak", "laktab:Laktab=child("),
        ("gwf-sfr", "sfrtab:Sfrtab=child("),
        ("gwt-ssm", "spc:Union[Spc,Spca]=child("),  # the file says which
    ],
)
def test_dfn_link_in_row_is_child(tmp_path, all_dfns, name, column):
    """A DFN file link in a list's row is a child column."""
    skip = {n for n in all_dfns if n != name}
    (spec,) = make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip, makedirs=True)
    assert column in "".join(spec.outpath.read_text().split())


def test_dfn_link_in_period_setting_stays_path(tmp_path, all_dfns):
    """SFR's period CROSS_SECTION setting still names its table file."""
    skip = {n for n in all_dfns if n != "gwf-sfr"}
    (spec,) = make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip, makedirs=True)
    assert "tab6_filename:Path=path(" in "".join(spec.outpath.read_text().split())


def test_observation_forms(tmp_path, all_dfns):
    """A component's observation types become a table of the forms their
    OBS ids take."""
    skip = {n for n in all_dfns if n not in ("gwf-csub", "gwf-uzf")}
    specs = {
        s.dfn_name: s
        for s in make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip, makedirs=True)
    }
    csub = specs["gwf-csub"].observations
    assert csub["csub"] == (("index",), ("string",))
    assert csub["csub-cell"] == (("cellid",),)
    assert csub["delay-head"] == (("index", "index"),)
    uzf = specs["gwf-uzf"].observations
    assert uzf["water-content"] == (("index", "double"), ("string", "double"))
    assert '"csub-cell": (("cellid",),),' in specs["gwf-csub"].outpath.read_text()


def test_list_block_dim_and_default(tmp_path, all_dfns):
    """A list block's row-count dimension (with any bound, in DFN shape
    syntax) and DFN default rows are emitted. Only a list whose shape names the dimension links to
    it: MAW's packagedata, not its shapeless connectiondata/angledata."""
    skip = {n for n in all_dfns if n not in ("sim-tdis", "utl-ats", "gwf-maw")}
    specs = {
        s.dfn_name: s
        for s in make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip, makedirs=True)
    }
    tdis = specs["sim-tdis"].outpath.read_text()
    assert 'dim="nper"' in tdis
    assert "default=((1.0, 1, 1.0),)," in tdis
    ats = specs["utl-ats"].outpath.read_text()
    assert 'dim="<=maxats"' in ats
    maw = build_component_spec(all_dfns["gwf-maw"], root=Path("/fake"))
    linked = {bp.block_name for bp in maw.block_properties if bp.dim_is_dfn_declared}
    assert linked == {"packagedata"}
    assert specs["gwf-maw"].outpath.read_text().count('dim="nmawwells"') == 1


def test_list_col_dim_only_from_shape(all_dfns):
    """A list links to a dimension only through its shape, with any bound
    operator stripped; a shapeless list isn't linked to a lone dimension."""
    from modflow_devtools.dfns.schema import List as ListField

    from flopy4.mf6.utils.codegen.filters import list_col_dim

    def lst(comp, block):
        return next(
            f for f in all_dfns[comp].blocks[block].fields.values() if isinstance(f, ListField)
        )

    assert list_col_dim(lst("utl-ats", "perioddata"), all_dfns["utl-ats"]) == "maxats"
    assert list_col_dim(lst("sim-tdis", "perioddata"), all_dfns["sim-tdis"]) == "nper"
    assert list_col_dim(lst("gwf-mvr", "packages"), all_dfns["gwf-mvr"]) == "maxpackages"
    # MAW's connectiondata has no shape; its one dimension (nmawwells) counts
    # wells, not connections
    assert list_col_dim(lst("gwf-maw", "connectiondata"), all_dfns["gwf-maw"]) is None


@pytest.mark.parametrize("name", ["gwf-oc", "prt-prp"])
def test_bounded_array_arm_is_variadic(tmp_path, all_dfns, name):
    """A bounded array arm (OC/PRP STEPS, shape ["<=nstp"]) stays a
    trailing-values tuple, not a fixed-length scalar column."""
    skip = {n for n in all_dfns if n != name}
    (spec,) = make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip, makedirs=True)
    assert "steps: tuple[int, ...] = field(default=(), array=True)" in spec.outpath.read_text()


@pytest.mark.parametrize(
    "field,fixed",
    [
        (Array(name="a", dtype="double", shape=["nseg"]), True),
        (Array(name="a", dtype="integer", shape=["<=nstp"]), False),
        (Array(name="a", dtype="string", shape=[]), False),
        (Double(name="a"), False),
    ],
)
def test_is_fixed_length_array(field, fixed):
    from flopy4.mf6.utils.codegen.filters import is_fixed_length_array

    assert is_fixed_length_array(field) == fixed


def test_scalar_columns_stay_scalar(tmp_path, all_dfns):
    """Only a variable-length array column becomes a trailing-values tuple."""
    skip = {n for n in all_dfns if n != "gwf-wel"}
    (spec,) = make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip, makedirs=True)
    assert "q: Union[float, str] = field(time_series=True)" in spec.outpath.read_text()


@pytest.mark.parametrize(
    "name,field,cls,keyword", [("gwf-chd", "ts", "Ts", "ts6"), ("utl-spca", "tas", "Tas", "tas6")]
)
def test_tagged_file_list_is_child_list(tmp_path, all_dfns, name, field, cls, keyword):
    """A linked tagged list of file records (TS6/TAS6 FILEIN) is a list of
    children, not a table filling the options block."""
    skip = {n for n in all_dfns if n != name}
    (spec,) = make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip, makedirs=True)
    assert "options" not in {bp.block_name for bp in spec.block_properties}
    # ignore whitespace: output is ruff-formatted only if ruff is installed
    text = "".join(spec.outpath.read_text().split())
    assert (
        f'{field}:list[{cls}]=child(block="options",keyword="{keyword}",direction="in",'
        "default=attrs.Factory(list))"
    ) in text


def test_tagged_file_list_is_repeatable_field(tmp_path, all_dfns, monkeypatch):
    """A tagged list of file records with no class to link to is a
    repeatable list[Path] options field."""
    make = importlib.import_module("flopy4.mf6.utils.codegen.make")
    monkeypatch.setattr(make, "_has_class", lambda *_: False)
    skip = {n for n in all_dfns if n != "gwf-chd"}
    (spec,) = make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip, makedirs=True)
    text = spec.outpath.read_text()
    assert "ts_file: Optional[list[Path]] = path(" in text
    assert "converter=attrs.converters.optional(to_list(Path))," in text


def test_tagged_record_list_roundtrip(tmp_path):
    """A tagged list of (non-file) records is a repeatable list[RecordClass]
    field: generated, loaded one element per line, and written back one line
    per element. No real DFN has one yet, so a synthetic one."""
    from modflow_devtools.dfns.schema import Block, Package
    from modflow_devtools.dfns.schema import List as ListField

    from flopy4.mf6.codec.reader import loads
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component

    dfn = Package(
        name="gwf-tlst",
        blocks={
            "options": Block(
                name="options",
                fields={
                    "print_input": Keyword(name="print_input", optional=True),
                    "scalerecord": ListField(
                        name="scalerecord",
                        optional=True,
                        item=Record(
                            name="scalerecord",
                            fields={
                                "scale": Keyword(name="scale"),
                                "factor": Double(name="factor", tagged=False),
                            },
                        ),
                    ),
                },
            ),
        },
    )
    (tmp_path / "gwf").mkdir()
    (spec,) = make_modules(dfns={"gwf-tlst": dfn}, outdir=tmp_path)
    text = spec.outpath.read_text()
    assert "scale: Optional[list[Scale]]" in text
    assert 'class Scale(Item):\n        _keyword: ClassVar[str] = "scale"' in text

    cls = _load_class_from_spec(spec, "gwf_tlst", "Tlst")
    pkg = structure_component(
        loads("BEGIN OPTIONS\n  SCALE 2.0\n  PRINT_INPUT\n  SCALE 3.0\nEND OPTIONS\n"), cls
    )
    assert [r.factor for r in pkg.scale] == [2.0, 3.0]
    lines = [line.strip() for line in dumps(unstructure_component(pkg)).splitlines()]
    assert [line for line in lines if line.startswith("SCALE")] == ["SCALE 2.0", "SCALE 3.0"]


def test_union_list_outside_period_roundtrip(tmp_path):
    """A list of unions gets the same arm classes and keyword dispatch in
    any block, not just the period block. No real DFN has one outside the
    period block yet, so a synthetic one."""
    from modflow_devtools.dfns.schema import Block, Package, Union
    from modflow_devtools.dfns.schema import List as ListField

    from flopy4.mf6.codec.reader import loads
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component

    def arm(name):
        return Record(
            name=f"{name}record",
            fields={
                name: Keyword(name=name),
                f"{name}_value": Double(name=f"{name}_value", tagged=False),
            },
        )

    dfn = Package(
        name="gwf-ulst",
        blocks={
            "options": Block(
                name="options",
                fields={
                    "print_input": Keyword(name="print_input", optional=True),
                    "settings": ListField(
                        name="settings",
                        optional=True,
                        item=Union(
                            name="setting",
                            arms={"raterecord": arm("rate"), "stagerecord": arm("stage")},
                        ),
                    ),
                },
            ),
        },
    )
    (tmp_path / "gwf").mkdir()
    (spec,) = make_modules(dfns={"gwf-ulst": dfn}, outdir=tmp_path)
    assert "settings: Optional[list[_SettingsItem]]" in spec.outpath.read_text()

    cls = _load_class_from_spec(spec, "gwf_ulst", "Ulst")
    pkg = structure_component(
        loads("BEGIN OPTIONS\n  RATE 2.0\n  PRINT_INPUT\n  STAGE 3.0\nEND OPTIONS\n"), cls
    )
    assert [type(s).__name__ for s in pkg.settings] == ["Rate", "Stage"]
    assert pkg.print_input
    lines = [line.strip() for line in dumps(unstructure_component(pkg)).splitlines()]
    assert [line for line in lines if line.startswith(("RATE", "STAGE"))] == [
        "RATE 2.0",
        "STAGE 3.0",
    ]


def test_auxiliary_is_string_array():
    """AUXILIARY is a string array in the DFN, and in the class: a list of
    names converts to one."""
    import numpy as np

    from flopy4.mf6.gwf import Wel

    assert Wel(auxiliary="conc").auxiliary.tolist() == ["conc"]
    wel = Wel(auxiliary=["conc", "temp"])
    assert isinstance(wel.auxiliary, np.ndarray)
    assert wel.auxiliary.tolist() == ["conc", "temp"]


def test_to_list_and_to_array():
    """A single value (str/path included) is wrapped; others convert per element."""
    import numpy as np

    from flopy4.mf6._types import to_array, to_list

    assert to_list(Path)("a.ts") == [Path("a.ts")]
    assert to_list(Path)(Path("a.ts")) == [Path("a.ts")]
    assert to_list(Path)(["a.ts", Path("b.ts")]) == [Path("a.ts"), Path("b.ts")]
    assert to_array(np.str_)("conc").tolist() == ["conc"]
    assert to_array(np.str_)(("conc", "temp")).tolist() == ["conc", "temp"]


@pytest.mark.parametrize(
    "type_str,expected",
    [
        ("Optional[Path]", "attrs.converters.optional(Path)"),
        ("Optional[list[Path]]", "attrs.converters.optional(to_list(Path))"),
        ("Optional[NDArray[np.str_]]", "attrs.converters.optional(to_array(np.str_))"),
        ("Optional[NDArray[np.float64]]", None),
        ("Optional[int]", None),
    ],
)
def test_converter_from_type(type_str, expected):
    from flopy4.mf6.utils.codegen.filters import converter

    assert converter(type_str) == expected


def test_layered_griddata_metadata():
    """Griddata arrays carry the DFN's `layered` flag; unset means False."""
    from flopy4.mf6.gwf.npf import Npf
    from flopy4.mf6.utl.ncf import Ncf

    assert attrs.fields_dict(Npf)["k"].metadata["layered"] is True
    assert not attrs.fields_dict(Ncf)["latitude"].metadata.get("layered", False)


def test_griddata_list_and_layered_values():
    """List griddata becomes an array; a layered array given one value per
    layer is repeated over each layer's cells."""
    from flopy4.mf6.gwf.npf import Npf

    assert isinstance(Npf(k=[1.0, 2.0]).k, np.ndarray)
    npf = Npf(k=[1.0, 2.0], dims={"nlay": 2, "ncpl": 3, "nodes": 6})
    np.testing.assert_array_equal(npf.k, [1.0, 1.0, 1.0, 2.0, 2.0, 2.0])
    npf = Npf(k=np.ones((2, 3)), dims={"nlay": 2, "nodes": 6})
    assert npf.k.shape == (6,)


def _load_class_from_spec(spec, mod_name: str, expected_class: str):
    """Generate, load, and return the class from a ComponentSpec. Cleans up module state."""
    mod_spec = importlib.util.spec_from_file_location(mod_name, spec.outpath)
    assert mod_spec is not None and mod_spec.loader is not None
    mod = importlib.util.module_from_spec(mod_spec)
    components_snapshot = dict(FNAMES)
    sys_modules_keys = set(sys.modules)
    try:
        mod_spec.loader.exec_module(mod)  # type: ignore[union-attr]
        assert hasattr(mod, expected_class), f"Class {expected_class} not found in {spec.outpath}"
        return getattr(mod, expected_class)
    finally:
        FNAMES.clear()
        FNAMES.update(components_snapshot)
        for key in set(sys.modules) - sys_modules_keys:
            del sys.modules[key]


def test_transport_tier_generates_importable_files(tmp_path, all_dfns):
    """gwt-disv, gwt-ist, gwe-disv generate importable Package subclasses."""
    for subdir in ("gwt", "gwe"):
        (tmp_path / subdir).mkdir()

    target = {n for n in TRANSPORT_TIER if n in all_dfns}
    skip = {n for n in all_dfns if n not in target}
    specs = make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip)
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


def test_oc_tier_generates_importable_files(tmp_path, all_dfns):
    """gwt-oc, gwe-oc, prt-oc generate importable Package subclasses with OC period fields."""
    for subdir in ("gwt", "gwe", "prt"):
        (tmp_path / subdir).mkdir()

    target = {n for n in OC_TIER if n in all_dfns}
    skip = {n for n in all_dfns if n not in target}
    specs = make_modules(dfns=all_dfns, outdir=tmp_path, skip=skip)
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
        # Verify the OC period arms (Save/Print, real typed classes) were generated
        arm_names = [ic.class_name for ic in spec.item_classes]
        assert {"Save", "Print"} <= set(arm_names), f"{dfn_name} should have Save/Print arm classes"
        # ocsetting's own arms (All/First/Last/Frequency/Steps) must be built
        # exactly once (shared by Save.ocsetting and Print.ocsetting, not
        # duplicated as e.g. SaverecordAll/PrintrecordAll -- see
        # make.py's _build_arm_specs_from_union nested_union_cache) and must
        # NOT be folded into the top-level Save|Print dispatch union.
        assert arm_names.count("All") == 1, f"{dfn_name}: ocsetting arms must not be duplicated"
        (period_union,) = [u for u in spec.item_unions if u.alias == "_StressPeriodDataItem"]
        top_level_names = set(period_union.members)
        assert top_level_names == {"Save", "Print"}, (
            f"{dfn_name}: only Save/Print may be top_level (dispatch union) arms"
        )
        nested_names = {ic.class_name for ic in spec.item_classes if not ic.top_level}
        assert nested_names == {"All", "First", "Last", "Frequency", "Steps"}


def test_utl_tier_generates_importable_files(tmp_path, all_dfns):
    """utl-* packages generate importable Package subclasses (including utl-tas inner classes)."""
    (tmp_path / "utl").mkdir()

    target = {n for n in UTL_TIER if n in all_dfns}
    skip = {n for n in all_dfns if n not in target}
    specs = make_modules(dfns=all_dfns, outdir=tmp_path, makedirs=True, skip=skip)
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


def test_exg_tier_generates_importable_files(tmp_path, all_dfns):
    """exg-* packages generate importable Exchange subclasses (including 0-field pass-only)."""
    (tmp_path / "exg").mkdir()

    target = {n for n in EXG_TIER if n in all_dfns}
    skip = {n for n in all_dfns if n not in target}
    specs = make_modules(dfns=all_dfns, outdir=tmp_path, makedirs=True, skip=skip)
    generated = {s.dfn_name: s for s in specs}

    from flopy4.mf6.exchange import Exchange

    for dfn_name, (expected_class, _) in EXG_TIER.items():
        if dfn_name not in all_dfns:
            continue
        assert dfn_name in generated, f"{dfn_name} was not generated"
        spec = generated[dfn_name]
        assert spec.outpath == tmp_path / "exg" / f"{expected_class.lower()}.py"
        cls = _load_class_from_spec(spec, f"_codegen_test_exg.{dfn_name}", expected_class)
        assert issubclass(cls, Exchange)


def test_aux_columns_follow_dfn():
    """An item has an aux column only where its DFN does, sized by the
    package's auxiliary names."""
    import attrs

    from flopy4.mf6.gwf import Buy, Lak, Wel

    assert attrs.fields_dict(Wel.StressPeriodData)["aux"].metadata["shape"] == ("auxiliary",)
    assert attrs.fields_dict(Lak.Packagedata)["aux"].metadata["shape"] == ("auxiliary",)
    # BUY has no AUXILIARY option and its packagedata no aux column
    assert "aux" not in attrs.fields_dict(Buy.Packagedata)


def test_sized_column_from_tokens():
    """A sized column takes as many tokens as its sizing field has values."""
    from flopy4.mf6.gwf import Wel

    tokens = [1, 2, 3, -5.0, 0.1, 0.2, "well1"]
    item = Wel.StressPeriodData.from_tokens(
        tokens, ncelldim=3, sizes={"auxiliary": 2}, boundnames=True
    )
    assert item.cellid == (0, 1, 2)
    assert item.q == -5.0
    assert item.aux == (0.1, 0.2)
    assert item.boundname == "well1"
    assert item.to_tokens() == tuple(tokens)


@pytest.mark.parametrize(
    "tokens,mnames",
    [
        (["sfr-1", 8, "sfr-2", 1, "FACTOR", 1.0], (None, None)),
        (["parent", "sfr-1", 8, "child", "sfr-2", 1, "FACTOR", 1.0], ("parent", "child")),
    ],
)
def test_optional_leading_columns(tokens, mnames):
    """MVR's optional model name columns come before its required ones."""
    from flopy4.mf6.gwf import Mvr

    item = Mvr.StressPeriodData.from_tokens(tokens)
    assert (item.mname1, item.mname2) == mnames
    assert (item.pname1, item.id1, item.pname2, item.id2) == ("sfr-1", 7, "sfr-2", 0)
    assert (item.mvrtype, item.value) == ("FACTOR", 1.0)
    assert item.to_tokens() == tuple(tokens)


def test_counted_array_column():
    """cell2d's icvert holds as many vertex indices as ncvert counts, each
    renumbered like an index column; ncvert defaults to len(icvert)."""
    from flopy4.mf6.gwf import Disv

    meta = attrs.fields_dict(Disv.Cell2d)["icvert"].metadata
    assert meta["array"] and meta["index"] and meta["shape"] == ("ncvert",)

    square = Disv.Cell2d.from_tokens([1, 0.5, 0.5, 4, 1, 2, 5, 4])
    assert square.icell2d == 0
    assert square.ncvert == 4
    assert square.icvert == (0, 1, 4, 3)
    assert square.to_tokens() == (1, 0.5, 0.5, 4, 1, 2, 5, 4)

    triangle = Disv.Cell2d(icell2d=1, xc=1.5, yc=0.5, icvert=(1, 2, 4))
    assert triangle.to_tokens() == (2, 1.5, 0.5, 3, 2, 3, 5)

    with pytest.raises(ValueError, match="ncvert=4"):
        Disv.Cell2d(icell2d=1, xc=1.5, yc=0.5, ncvert=4, icvert=(1, 2, 4)).to_tokens()

    disv = Disv(
        nlay=1,
        top=1.0,
        botm=0.0,
        vertices=[(0, 0.0, 0.0), (1, 1.0, 0.0), (2, 1.0, 1.0), (3, 0.0, 1.0)],
        cell2d=[(0, 0.5, 0.5, 4, (0, 1, 2, 3))],
    )
    assert (disv.ncpl, disv.nvert) == (1, 4)
    assert disv.cell2d[0].icvert == (0, 1, 2, 3)
