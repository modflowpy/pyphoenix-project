import json
from importlib.metadata import Distribution

from beartype.claw import beartype_this_package

_PKG_URL = Distribution.from_name("flopy4").read_text("direct_url.json")
_EDITABLE = json.loads(_PKG_URL).get("dir_info", {}).get("editable", False)
if _EDITABLE:
    beartype_this_package()
