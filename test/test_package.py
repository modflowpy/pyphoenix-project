from flopy4.array import MFArray
from flopy4.block import MFBlock
from flopy4.package import MFPackage
from flopy4.scalar import MFDouble, MFFilename, MFInteger, MFKeyword, MFString


class TestPackage(MFPackage):
    __test__ = False  # tell pytest not to collect

    k = MFKeyword(
        block="options",
        description="keyword",
    )
    i = MFInteger(
        block="options",
        description="int",
    )
    d = MFDouble(
        block="options",
        description="double",
    )
    s = MFString(block="options", description="string", optional=False)
    f = MFFilename(block="options", description="filename", optional=False)
    a = MFArray(block="packagedata", description="array", shape=(3))


def test_member_params():
    params = TestPackage.params
    assert len(params) == 6

    k = params.k
    assert isinstance(k, MFKeyword)
    assert k.block == "options"
    assert k.description == "keyword"
    assert k.optional

    i = params.i
    assert isinstance(i, MFInteger)
    assert i.block == "options"
    assert i.description == "int"
    assert i.optional

    d = params.d
    assert isinstance(d, MFDouble)
    assert d.block == "options"
    assert d.description == "double"
    assert d.optional

    s = params.s
    assert isinstance(s, MFString)
    assert s.block == "options"
    assert s.description == "string"
    assert not s.optional

    f = params.f
    assert isinstance(f, MFFilename)
    assert f.block == "options"
    assert f.description == "filename"
    assert not f.optional

    a = params.a
    assert isinstance(a, MFArray)
    assert a.block == "packagedata"
    assert a.description == "array"


def test_member_blocks():
    blocks = TestPackage.blocks
    assert len(blocks) == 2

    block = blocks.options
    assert isinstance(block, MFBlock)
    assert len(block.params) == 5

    k = block["k"]
    assert isinstance(k, MFKeyword)
    assert k.description == "keyword"
    assert k.optional

    i = block["i"]
    assert isinstance(i, MFInteger)
    assert i.description == "int"
    assert i.optional

    d = block["d"]
    assert isinstance(d, MFDouble)
    assert d.description == "double"
    assert d.optional

    s = block["s"]
    assert isinstance(s, MFString)
    assert s.description == "string"
    assert not s.optional

    f = block["f"]
    assert isinstance(f, MFFilename)
    assert f.description == "filename"
    assert not f.optional

    block = blocks.packagedata
    assert isinstance(block, MFBlock)
    assert len(block.params) == 1

    a = block["a"]
    assert isinstance(a, MFArray)
    assert a.description == "array"


def test_load_write(tmp_path):
    name = "test"
    fpth = tmp_path / f"{name}.txt"
    array = " ".join(str(x) for x in [1.0, 2.0, 3.0])
    with open(fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("  K\n")
        f.write("  I 1\n")
        f.write("  D 1.0\n")
        f.write("  S value\n")
        f.write(f"  F FILEIN {fpth}\n")
        f.write("END OPTIONS\n")
        f.write("\n")
        f.write("BEGIN PACKAGEDATA\n")
        f.write(f"  A\nINTERNAL\n{array}\n")
        f.write("END PACKAGEDATA\n")

    # test package load
    with open(fpth, "r") as f:
        package = TestPackage.load(f)

        assert len(package.blocks) == 2
        assert len(package.params) == 6

        # class attribute as param specification
        assert isinstance(TestPackage.k, MFKeyword)
        assert TestPackage.k.name == "k"
        assert TestPackage.k.block == "options"
        assert TestPackage.k.description == "keyword"

        # instance attribute as shortcut to param value
        assert isinstance(package.k, bool)
        assert package.k
        assert package.i == 1
        assert package.d == 1.0
        assert package.s == "value"
        assert package.f == fpth

    # test package write
    fpth2 = tmp_path / f"{name}2.txt"
    with open(fpth2, "w") as f:
        package.write(f)
    with open(fpth2, "r") as f:
        lines = f.readlines()
        assert "BEGIN OPTIONS \n" in lines
        assert "  K\n" in lines
        assert "  I 1\n" in lines
        assert "  D 1.0\n" in lines
        assert "  S value\n" in lines
        assert f"  F FILEIN {fpth}\n" in lines
        # todo check array
        assert "END OPTIONS\n" in lines
