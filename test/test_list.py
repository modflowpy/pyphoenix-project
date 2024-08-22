import numpy as np

from flopy4.block import MFBlock
from flopy4.compound import MFList
from flopy4.scalar import MFDouble, MFInteger
from flopy4.simulation import MFSimulation


class TestBlock(MFBlock):
    __test__ = False  # tell pytest not to collect

    testblock = MFList(
        params={
            # "s": MFString(),
            "s": MFInteger(),
            "i": MFInteger(),
            "d": MFDouble(),
        },
        description="recarray",
        optional=False,
    )


def test_tl(tmp_path):
    tlist = [False, 0, "temp", 1.0, True]
    assert isinstance(tlist[0], bool)
    assert isinstance(tlist[1], int)
    assert isinstance(tlist[2], str)
    assert isinstance(tlist[3], float)
    assert isinstance(tlist[4], bool)


def test_list_load(tmp_path):
    name = "testblock"

    fpth = tmp_path / f"{name}.txt"
    with open(fpth, "w") as f:
        f.write("BEGIN TESTBLOCK\n")
        f.write("  0 1  2.\n")
        f.write("  1 2  3.\n")
        f.write("  1 2  3.\n")
        f.write("END TESTBLOCK\n")

    with open(fpth, "r") as f:
        in_list = TestBlock.load(f)
        assert in_list.name == name
        # assert isinstance(TestBlock.blist.params["s"], MFString)
        assert isinstance(TestBlock.testblock.params["i"], MFInteger)
        assert isinstance(TestBlock.testblock.params["d"], MFDouble)
        assert isinstance(in_list.params["testblock"]["i"], np.ndarray)
        assert isinstance(in_list.params["testblock"]["d"], np.ndarray)


def test_sim_load(tmp_path):
    name = "gwf_1"

    nlay = 3
    nrow = 10
    ncol = 10
    dis_fpth = tmp_path / f"{name}.dis"
    with open(dis_fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("END OPTIONS\n\n")
        f.write("BEGIN DIMENSIONS\n")
        f.write(f"  NLAY  {nlay}\n")
        f.write(f"  NROW  {nrow}\n")
        f.write(f"  NCOL  {ncol}\n")
        f.write("END DIMENSIONS\n\n")
        f.write("BEGIN GRIDDATA\n")
        f.write("  DELR\n    CONSTANT  1000.00000000\n")
        f.write("  DELC\n    CONSTANT  2000.00000000\n")
        f.write("  TOP\n    CONSTANT  0.00000000\n")
        f.write("  BOTM    LAYERED\n")
        f.write("    CONSTANT  -100.00000000\n")
        f.write("    CONSTANT  -150.00000000\n")
        f.write("    CONSTANT  -350.00000000\n")
        f.write("END GRIDDATA\nn\\n")

    ic_fpth = tmp_path / f"{name}.ic"
    strt = np.linspace(0.0, 30.0, num=300)
    array = " ".join(str(x) for x in strt)
    with open(ic_fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("  EXPORT_ARRAY_ASCII\n")
        f.write("END OPTIONS\n")
        f.write("\n")
        f.write("BEGIN GRIDDATA\n")
        f.write(f"  STRT\n    INTERNAL\n      {array}\n")
        f.write("END GRIDDATA\n")

    nam_fpth = tmp_path / f"{name}.nam"
    with open(nam_fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("END OPTIONS\n")
        f.write("\n")
        f.write("BEGIN PACKAGES\n")
        f.write(f"  DIS6  {tmp_path}/{name}.dis  dis\n")
        f.write(f"  IC6  {tmp_path}/{name}.ic  ic\n")
        f.write("END PACKAGES\n")

    tdis_fpth = tmp_path / "sim.tdis"
    with open(tdis_fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("  TIME_UNITS  days\n")
        f.write("  START_DATE_TIME  2041-01-01t00:00:00-05:00\n")
        f.write("END OPTIONS\n\n")
        f.write("BEGIN DIMENSIONS\n")
        f.write("  NPER  1\n")
        f.write("END DIMENSIONS\n\n")
        f.write("BEGIN PERIODDATA\n")
        f.write("    1.00000000  1       1.00000000\n")
        f.write("END PERIODDATA\n")

    sim_fpth = tmp_path / "mfsim.nam"
    with open(sim_fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("END OPTIONS\n\n")
        f.write("BEGIN TIMING\n")
        f.write(f"  TDIS6  {tmp_path}/sim.tdis\n")
        f.write("END TIMING\n\n")
        f.write("BEGIN MODELS\n")
        f.write(f"  gwf6  {tmp_path}/{name}.nam  {name}\n")
        f.write("END MODELS\n\n")
        f.write("BEGIN EXCHANGES\n")
        f.write("END EXCHANGES\n\n")
        f.write("BEGIN SOLUTIONGROUP 1\n")
        f.write("END SOLUTIONGROUP 1\n\n")

    # test resolve
    with open(sim_fpth, "r") as f:
        MFSimulation.load(f)
