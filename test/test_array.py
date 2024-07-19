import numpy as np

from flopy4.array import MFArray


def test_array_load_1d(tmp_path):
    name = "array"
    fpth = tmp_path / f"{name}.txt"
    how = "INTERNAL"
    v = [1.0, 2.0, 3.0]
    value = " ".join(str(x) for x in v)
    with open(fpth, "w") as f:
        f.write(f"{name.upper()}\n{how}\n{value}\n")

    with open(fpth, "r") as f:
        array = MFArray.load(f, cwd=tmp_path, shape=(3))
        assert array.name == name
        assert np.allclose(array.value, np.array(v))


def test_array_load_3d(tmp_path):
    name = "array"
    fpth = tmp_path / f"{name}.txt"
    how = "INTERNAL"
    v = [[[1.0, 2.0, 3.0]], [[4.0, 5.0, 6.0]], [[7.0, 8.0, 9.0]]]
    value = ""
    for a in v:
        for b in a:
            value += " ".join(str(x) for x in b)
            value += " "
    with open(fpth, "w") as f:
        f.write(f"{name.upper()}\n{how}\n{value}\n")

    with open(fpth, "r") as f:
        array = MFArray.load(f, cwd=tmp_path, shape=(3, 1, 3))
        assert array.name == name
        assert np.allclose(array.value, np.array(v))


def test_array_load_layered(tmp_path):
    name = "array"
    fpth = tmp_path / f"{name}.txt"
    how = "INTERNAL"
    v = [[[1.0, 2.0, 3.0]], [[4.0, 5.0, 6.0]], [[7.0, 8.0, 9.0]]]
    value = ""
    for a in v:
        for b in a:
            # TODO: MFArray expects this on separate line
            value += f"{how}\n"
            value += " ".join(str(x) for x in b)
            value += "\n"
    with open(fpth, "w") as f:
        f.write(f"{name.upper()} LAYERED\n{value}")

    with open(fpth, "r") as f:
        array = MFArray.load(f, cwd=tmp_path, shape=(3, 1, 3))
        assert array.name == name
        assert np.allclose(array.value, np.array(v))
