from flopy4.block import MFBlock, get_member_params
from flopy4.scalar import MFDouble, MFFilename, MFInteger, MFKeyword, MFString


class TestBlock(MFBlock):
    __test__ = False  # tell pytest not to collect

    k = MFKeyword(description="keyword")
    i = MFInteger(description="int")
    d = MFDouble(description="double")
    s = MFString(description="string", optional=False)
    f = MFFilename(description="filename", optional=False)
    # a = MFArray(description="array")


def test_get_member_params():
    params = get_member_params(TestBlock)
    assert len(params) == 5

    k = params["k"]
    assert isinstance(k, MFKeyword)
    assert k.description == "keyword"
    assert k.optional

    i = params["i"]
    assert isinstance(i, MFInteger)
    assert i.description == "int"
    assert i.optional

    d = params["d"]
    assert isinstance(d, MFDouble)
    assert d.description == "double"
    assert d.optional

    s = params["s"]
    assert isinstance(s, MFString)
    assert s.description == "string"
    assert not s.optional

    f = params["f"]
    assert isinstance(f, MFFilename)
    assert f.description == "filename"
    assert not f.optional

    # a = params["a"]
    # assert isinstance(f, MFArray)
    # assert f.description == "array"
    # assert not f.optional


def test_block_load_write_no_index(tmp_path):
    name = "options"
    fpth = tmp_path / f"{name}.txt"
    with open(fpth, "w") as f:
        f.write(f"BEGIN {name.upper()}\n")
        f.write("  K\n")
        f.write("  I 1\n")
        f.write("  D 1.0\n")
        f.write("  S value\n")
        f.write(f"  F FILEIN {fpth}\n")
        f.write(f"END {name.upper()}\n")

    # test block load
    with open(fpth, "r") as f:
        block = TestBlock.load(f)

        # class attributes: param specifications
        assert isinstance(TestBlock.k, MFKeyword)
        assert TestBlock.k.name == "k"
        assert TestBlock.k.block == "options"
        assert TestBlock.k.description == "keyword"

        # instance attributes: shortcut access to param values
        assert isinstance(block.k, bool)
        assert block.k
        assert block.i == 1
        assert block.d == 1.0
        assert block.s == "value"
        assert block.f == fpth

    # test block write
    fpth2 = tmp_path / f"{name}2.txt"
    with open(fpth2, "w") as f:
        block.write(f)
    with open(fpth2, "r") as f:
        lines = f.readlines()
        assert "  K\n" in lines
        assert "  I 1\n" in lines
        assert "  D 1.0\n" in lines
        assert "  S value\n" in lines
        assert f"  F FILEIN {fpth}\n" in lines
