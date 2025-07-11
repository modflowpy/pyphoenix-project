from flopy4.mf6.modflow.gwf import Gwf
from flopy4.mf6.spec import blocks, blocks_dict


def test_blocks():
    block_spec = blocks(Gwf)
    options = block_spec[0]
    assert options[-1].name == "nc_filerecord"


def test_blocks_dict():
    block_spec = blocks_dict(Gwf)
    options = block_spec["options"]
    assert "save_flows" in options
