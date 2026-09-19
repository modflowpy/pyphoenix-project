import pytest
from modflow_devtools.dfns.schema import (
    Array,
    Block,
    Double,
    Integer,
    Keyword,
    List,
    Package,
    Record,
    String,
    Union,
)

from flopy4.mf6.codec.reader.grammar import make_grammar, make_grammars


@pytest.fixture
def minimal_dfn():
    """Create a minimal component for testing."""
    return Package(
        name="test-component",
        blocks={
            "options": Block(
                name="options",
                fields={"test_field": Keyword(name="test_field")},
            )
        },
    )


@pytest.fixture
def simple_dfn():
    """Create a simple component with various field types."""
    return Package(
        name="gwf-test",
        blocks={
            "options": Block(
                name="options",
                fields={"export_ascii": Keyword(name="export_array_ascii")},
            ),
            "griddata": Block(
                name="griddata",
                fields={"strt": Array(name="strt", dtype="double", shape=["nodes"])},
            ),
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
    assert "start: _NL* (block _NL*)*" in content
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

    dfns = {"test1": Package(name="test1", blocks={})}

    make_grammars(dfns, outdir)
    assert outdir.exists()
    assert outdir.is_dir()

    dfns = {
        "comp1": Package(name="comp1", blocks={}),
        "comp2": Package(name="comp2", blocks={}),
        "comp3": Package(name="comp3", blocks={}),
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
    dfn = Package(
        name="gwf-test",
        blocks={
            "options": Block(
                name="options",
                fields={"print_input": Keyword(name="print_input")},
            ),
            "period": Block(
                name="period",
                header=Integer(name="iper"),
                fields={
                    "stress_period_data": List(
                        name="stress_period_data",
                        shape=["maxbound"],
                        item=Record(
                            name="stress_period_data",
                            fields={
                                "q": Double(name="q"),
                                "aux": Double(name="aux"),
                            },
                        ),
                    )
                },
            ),
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
    assert "record" in stress_period_data_line


def test_make_grammar_with_named_subfields(tmp_path):
    dfn = Package(
        name="gwf-rch",
        blocks={
            "period": Block(
                name="period",
                header=Integer(name="iper"),
                fields={
                    "stress_period_data": List(
                        name="stress_period_data",
                        shape=["maxbound"],
                        item=Record(
                            name="stress_period_data",
                            fields={"recharge": Double(name="recharge")},
                        ),
                    )
                },
            ),
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
    dfn = Package(
        name="gwf-oc",
        blocks={
            "period": Block(
                name="period",
                header=Integer(name="iper"),
                fields={
                    "output": List(
                        name="output",
                        item=Union(
                            name="output",
                            arms={
                                "saverecord": Record(
                                    name="saverecord",
                                    fields={
                                        "save": Keyword(name="save"),
                                        "rtype": String(name="rtype", tagged=False),
                                        "ocsetting": Union(
                                            name="ocsetting",
                                            arms={
                                                "all": Keyword(name="all"),
                                                "first": Keyword(name="first"),
                                                "last": Keyword(name="last"),
                                            },
                                        ),
                                    },
                                ),
                            },
                        ),
                    )
                },
            )
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
