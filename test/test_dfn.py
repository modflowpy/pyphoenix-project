from pathlib import Path

import pytest

from flopy4.dfn import Dfn

PROJ_ROOT = Path(__file__).parents[1]
DFN_PATH = PROJ_ROOT / "spec" / "dfn"
DFN_NAMES = [
    dfn.stem for dfn in DFN_PATH.glob("*.dfn") if dfn.stem not in ["common", "flopy"]
]


@pytest.mark.parametrize("dfn_name", DFN_NAMES)
def test_dfn_load(dfn_name):
    with (
        open(DFN_PATH / "common.dfn", "r") as common_file,
        open(DFN_PATH / f"{dfn_name}.dfn", "r") as dfn_file,
    ):
        name = Dfn.Name.parse(dfn_name)
        common, _ = Dfn._load_v1_flat(common_file)
        dfn = Dfn.load(dfn_file, name=name, common=common)
        assert any(dfn)
