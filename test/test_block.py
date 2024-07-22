import numpy as np

from flopy4.array import MFArray
from flopy4.block import MFBlock
from flopy4.compound import MFRecord
from flopy4.scalar import MFDouble, MFFilename, MFInteger, MFKeyword, MFString


class TestBlock(MFBlock):
    __test__ = False  # tell pytest not to collect

    k = MFKeyword(description="keyword")
    i = MFInteger(description="int")
    d = MFDouble(description="double")
    s = MFString(description="string", optional=False)
    f = MFFilename(description="filename", optional=False)
    a = MFArray(description="array", shape=(3))
    r = MFRecord(
        scalars=[
            MFKeyword(name="rk", description="keyword"),
            MFInteger(name="ri", description="int"),
            MFDouble(name="rd", description="double"),
        ],
        description="record",
        optional=False,
    )


def test_members():
    params = TestBlock.params
    assert len(params) == 7

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

    a = params["a"]
    assert isinstance(a, MFArray)
    assert a.description == "array"
    assert a.optional

    r = params["r"]
    assert isinstance(r, MFRecord)
    assert r.description == "record"
    assert not r.optional


def test_load_write(tmp_path):
    name = "options"
    fpth = tmp_path / f"{name}.txt"
    with open(fpth, "w") as f:
        f.write(f"BEGIN {name.upper()}\n")
        f.write("  K\n")
        f.write("  I 1\n")
        f.write("  D 1.0\n")
        f.write("  S value\n")
        f.write(f"  F FILEIN {fpth}\n")
        f.write("  R RK RI 2 RD 2.0\n")
        f.write("  A\n    INTERNAL\n      1.0 2.0 3.0\n")
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
        assert np.allclose(block.a, np.array([1.0, 2.0, 3.0]))

        assert isinstance(TestBlock.r, MFRecord)
        assert TestBlock.r.name == "r"
        assert len(TestBlock.r.scalars) == 3
        assert isinstance(TestBlock.r.scalars[0], MFKeyword)
        assert isinstance(TestBlock.r.scalars[1], MFInteger)
        assert isinstance(TestBlock.r.scalars[2], MFDouble)

        assert isinstance(block.r, tuple)
        assert block.r == (True, 2, 2.0)

    # test block write
    fpth2 = tmp_path / f"{name}2.txt"
    with open(fpth2, "w") as f:
        block.write(f)
    with open(fpth2, "r") as f:
        lines = f.readlines()
        assert "BEGIN OPTIONS \n" in lines
        assert "  K\n" in lines
        assert "  I 1\n" in lines
        assert "  D 1.0\n" in lines
        assert "  S value\n" in lines
        assert f"  F FILEIN {fpth}\n" in lines
        # assert "  A\n    INTERNAL\n      1.0 2.0 3.0\n" in lines
        assert "  R  RK  RI 2  RD 2.0\n" in lines
        assert "END OPTIONS\n" in lines
