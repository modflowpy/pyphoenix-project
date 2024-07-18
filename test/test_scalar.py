import pytest

from flopy4.scalar import MFDouble, MFFilename, MFInteger, MFKeyword


def test_keyword_load(tmp_path):
    name = "keyword"
    fpth = tmp_path / f"{name}.txt"
    with open(fpth, "w") as f:
        f.write(name.upper() + "\n")

    with open(fpth, "r") as f:
        scalar = MFKeyword.load(f)
        assert scalar.name == name
        assert scalar.value


def test_keyword_load_empty(tmp_path):
    name = "keyword"
    fpth = tmp_path / f"{name}.txt"
    fpth.touch()

    with open(fpth, "r") as f:
        with pytest.raises(ValueError):
            MFKeyword.load(f)


def test_integer_load(tmp_path):
    name = "integer"
    fpth = tmp_path / f"{name}.txt"
    value = 1
    with open(fpth, "w") as f:
        f.write(f"{name.upper()} {value} \n")

    with open(fpth, "r") as f:
        scalar = MFInteger.load(f)
        assert scalar.name == name
        assert scalar.value == value


def test_double_load(tmp_path):
    name = "double"
    fpth = tmp_path / f"{name}.txt"
    value = 1.0
    with open(fpth, "w") as f:
        f.write(f"{name.upper()} {value} \n")

    with open(fpth, "r") as f:
        scalar = MFDouble.load(f)
        assert scalar.name == name
        assert scalar.value == value


def test_filename_load(tmp_path):
    name = "filename"
    fpth = tmp_path / f"{name}.txt"
    value = fpth
    with open(fpth, "w") as f:
        f.write(f"{name.upper()} FILEIN {value} \n")

    with open(fpth, "r") as f:
        scalar = MFFilename.load(f)
        assert scalar.name == name
        assert scalar.value == value
