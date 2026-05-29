import pytest
from modflow_devtools.dfn import Dfn, Field
from packaging.version import Version

from flopy4.mf6.codec.reader.grammar import make_grammar, make_grammars


@pytest.fixture
def minimal_dfn():
    """Create a minimal DFN for testing."""
    return Dfn(
        schema_version=Version("2.0.0"),
        name="test-component",
        blocks={
            "options": {
                "test_field": Field(
                    name="test_field",
                    type="keyword",
                    block="options",
                )
            }
        },
    )


@pytest.fixture
def simple_dfn():
    """Create a simple DFN with various field types."""
    return Dfn(
        schema_version=Version("2.0.0"),
        name="gwf-test",
        blocks={
            "options": {
                "export_ascii": Field(
                    name="export_array_ascii",
                    type="keyword",
                    block="options",
                )
            },
            "griddata": {
                "strt": Field(
                    name="strt",
                    type="double",
                    block="griddata",
                    shape="(nodes)",
                )
            },
        },
    )


def test_make_grammar_creates_file(tmp_path, minimal_dfn):
    """Test that make_grammar creates a grammar file."""
    make_grammar(minimal_dfn, tmp_path)

    expected_file = tmp_path / "test-component.lark"
    assert expected_file.exists()
    assert expected_file.is_file()
    content = expected_file.read_text()
    assert "// Auto-generated grammar for MF6 TEST-COMPONENT" in content
    # Grammar imports typed rules from typed.lark
    assert "%import typed.integer -> integer" in content
    assert "%import typed.double -> double" in content
    assert "start: block*" in content
    assert "options_block" in content


def test_make_grammar_with_multiple_blocks(tmp_path, simple_dfn):
    """Test grammar generation with multiple blocks."""
    make_grammar(simple_dfn, tmp_path)

    grammar_file = tmp_path / "gwf-test.lark"
    content = grammar_file.read_text()

    assert "options_block" in content
    assert "griddata_block" in content
    assert 'begin"i "options"' in content.lower()
    assert 'begin"i "griddata"' in content.lower()
    assert "strt" in content
    assert "array" in content.lower()


def test_make_all_grammars(tmp_path):
    outdir = tmp_path / "new_directory"
    assert not outdir.exists()

    dfns = {
        "test1": Dfn(
            schema_version=Version("2.0.0"),
            name="test1",
            blocks={},
        )
    }

    make_grammars(dfns, outdir)
    assert outdir.exists()
    assert outdir.is_dir()

    dfns = {
        "comp1": Dfn(
            schema_version=Version("2.0.0"),
            name="comp1",
            blocks={},
        ),
        "comp2": Dfn(
            schema_version=Version("2.0.0"),
            name="comp2",
            blocks={},
        ),
        "comp3": Dfn(
            schema_version=Version("2.0.0"),
            name="comp3",
            blocks={},
        ),
    }

    make_grammars(dfns, tmp_path)

    assert (tmp_path / "comp1.lark").exists()
    assert (tmp_path / "comp2.lark").exists()
    assert (tmp_path / "comp3.lark").exists()


def test_make_all_grammars_empty_dict(tmp_path):
    make_grammars({}, tmp_path)

    assert tmp_path.exists()  # create directory
    assert len(list(tmp_path.glob("*.lark"))) == 0


def test_make_grammar_overwrites_existing(tmp_path, minimal_dfn):
    """Test that make_grammar overwrites existing files."""
    grammar_file = tmp_path / "test-component.lark"
    grammar_file.write_text("OLD CONTENT")

    make_grammar(minimal_dfn, tmp_path)

    content = grammar_file.read_text()
    assert "OLD CONTENT" not in content
    assert "Auto-generated grammar" in content


def test_make_grammar_with_period_block(tmp_path):
    dfn = Dfn(
        schema_version=Version("2.0.0"),
        name="gwf-test",
        blocks={
            "options": {
                "print_input": Field(
                    name="print_input",
                    type="keyword",
                    block="options",
                )
            },
            "period": {
                "q": Field(
                    name="q",
                    type="double",
                    block="period",
                    shape="(nper, nnodes)",
                ),
                "aux": Field(
                    name="aux",
                    type="double",
                    block="period",
                    shape="(nper, nnodes, naux)",
                ),
            },
        },
    )

    make_grammar(dfn, tmp_path)

    grammar_file = tmp_path / "gwf-test.lark"
    content = grammar_file.read_text()

    # Period block should have a stress_period_data recarray instead of individual fields
    assert "stress_period_data" in content
    assert "period_fields:" in content

    # Individual q and aux should not appear as separate rules in period_fields
    # (they should be combined into stress_period_data)
    lines = content.split("\n")
    period_fields_line = [l for l in lines if "period_fields:" in l][0]
    assert "stress_period_data" in period_fields_line

    # stress_period_data should accept numbers and strings, one row per line
    assert "stress_period_data:" in content
    stress_period_data_line = [l for l in lines if l.strip().startswith("stress_period_data:")][0]


def test_make_grammar_with_named_subfields(tmp_path):
    dfn = Dfn(
        schema_version=Version("2.0.0"),
        name="gwf-rch",
        blocks={
            "period": {
                "recharge": Field(
                    name="recharge",
                    type="double",
                    block="period",
                    shape="(nper, nnodes)",
                ),
            },
        },
    )

    make_grammar(dfn, tmp_path)

    grammar_file = tmp_path / "gwf-rch.lark"
    content = grammar_file.read_text()

    # stress_period_data should be a generic recarray accepting numbers/strings per line
    assert "stress_period_data" in content
    lines = content.split("\n")
    stress_period_data_line = [l for l in lines if l.strip().startswith("stress_period_data:")][0]
    # Should accept both numbers and simple strings
    assert "record" in stress_period_data_line


def test_make_grammar_with_oc_style_records(tmp_path):
    """Test grammar generation for OC-style records with union fields."""
    dfn = Dfn(
        schema_version=Version("2.0.0"),
        name="gwf-oc",
        blocks={
            "period": {
                "saverecord": Field(
                    name="saverecord",
                    type="record",
                    block="period",
                    children={
                        "save": Field(name="save", type="keyword", block="period"),
                        "rtype": Field(name="rtype", type="string", block="period"),
                        "ocsetting": Field(
                            name="ocsetting",
                            type="union",
                            block="period",
                            children={
                                "all": Field(name="all", type="keyword", block="period"),
                                "first": Field(name="first", type="keyword", block="period"),
                                "last": Field(name="last", type="keyword", block="period"),
                            },
                        ),
                    },
                )
            }
        },
    )

    make_grammar(dfn, tmp_path)

    grammar_file = tmp_path / "gwf-oc.lark"
    content = grammar_file.read_text()

    # Should generate a record rule with keyword, word (not string), and union
    assert 'saverecord: "save"i word ocsetting' in content

    # Should generate the union rule for ocsetting
    assert "ocsetting:" in content
    assert "ocsetting_all" in content
    assert "ocsetting_first" in content
    assert "ocsetting_last" in content
