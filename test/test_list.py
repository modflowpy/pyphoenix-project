import numpy as np

from flopy4.block import MFBlock
from flopy4.compound import MFList
from flopy4.scalar import MFDouble, MFInteger, MFString


class TestBlock(MFBlock):
    __test__ = False  # tell pytest not to collect

    testblock = MFList(
        params={
            "s": MFString(),
            "i": MFInteger(),
            "d": MFDouble(),
        },
        description="recarray",
        optional=False,
    )


class SolutionGroup(MFBlock):
    __test__ = False  # tell pytest not to collect

    slntype = MFString(
        block="solutiongroup", shape="", optional=False, description=""
    )

    slnfname = MFString(
        block="solutiongroup", shape="", optional=False, description=""
    )

    slnmnames = MFString(
        block="solutiongroup", shape="(:)", optional=False, description=""
    )

    solutiongroup = MFList(
        params={
            "slntype": slntype,
            "slnfname": slnfname,
            "slnmnames": slnmnames,
        },
        block="solutiongroup",
        shape="",
        optional=False,
        description="",
    )


def test_list_load1(tmp_path):
    name = "testblock"

    fpth = tmp_path / f"{name}.txt"
    with open(fpth, "w") as f:
        f.write("BEGIN TESTBLOCK\n")
        f.write("  model 1  2.\n")
        f.write("  exch 2  3.\n")
        f.write("  sim 2  3.\n")
        f.write("END TESTBLOCK\n")

    in_list = None
    with open(fpth, "r") as f:
        in_list = TestBlock.load(f)

    assert in_list.name == name
    assert isinstance(TestBlock.testblock.params["s"], MFString)
    assert isinstance(TestBlock.testblock.params["i"], MFInteger)
    assert isinstance(TestBlock.testblock.params["d"], MFDouble)
    assert isinstance(in_list.params["testblock"]["s"], list)
    assert isinstance(in_list.params["testblock"]["i"], np.ndarray)
    assert isinstance(in_list.params["testblock"]["d"], np.ndarray)
    assert isinstance(in_list.params["testblock"]["s"][0], str)
    assert isinstance(in_list.params["testblock"]["i"][0], np.int32)
    assert isinstance(in_list.params["testblock"]["d"][0], np.float64)
    assert in_list.params["testblock"]["s"] == ["model", "exch", "sim"]
    assert np.allclose(in_list.params["testblock"]["i"], np.array([1, 2, 2]))
    assert np.allclose(
        in_list.params["testblock"]["d"], np.array([2.0, 3.0, 3.0])
    )


def test_list_load2(tmp_path):
    name = "solutiongroup"

    fpth = tmp_path / f"{name}.txt"
    with open(fpth, "w") as f:
        f.write("BEGIN SOLUTIONGROUP 1\n")
        f.write(
            f"  ims6  {tmp_path}/{name}.ims  "
            f"model0 model1 model2 model3 model4\n"
        )
        f.write("END SOLUTIONGROUP 1\n\n")

    in_list = None
    with open(fpth, "r") as f:
        in_list = SolutionGroup.load(f)

    assert in_list.name == name
    assert in_list.params["solutiongroup"]["slntype"] == ["ims6"]
    assert in_list.params["solutiongroup"]["slnfname"] == [
        f"{tmp_path}/{name}.ims"
    ]
    assert in_list.params["solutiongroup"]["slnmnames"] == [
        "model0 model1 model2 model3 model4"
    ]
