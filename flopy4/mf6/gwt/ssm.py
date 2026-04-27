# Hand-written; kept out of codegen (_SKIP) because the v2 TOML DFN conversion
# drops the SOURCES block, which MF6 requires to be present even when empty.
# Limitation: the sources recarray (pname/srctype/auxname) is not implemented.
# Specifying source concentrations via auxiliary variables requires a full
# recarray field that is not yet supported by the flopy4 codec.
from typing import Optional

from xattree import xattree

from flopy4.mf6.package import Package
from flopy4.mf6.spec import field


@xattree
class Ssm(Package):
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    # Placeholder ensures the required SOURCES block is written (even when empty).
    sources: Optional[str] = field(block="sources", default=None)
