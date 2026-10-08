"""mypy plugin: let mypy's attrs plugin read the converters of fields
declared with flopy4's `field()`/`path()` wrappers, so a constructor
takes what a field's converter accepts (``Gwf(newtonoptions=True)``,
``Oc(budget_file="x.cbc")``). Enable it in a mypy config::

    [tool.mypy]
    plugins = ["flopy4.mypy_plugin"]

`attr_attrib_makers` is a mypy internal, not a public hook, so a mypy
release could break this.
"""

import mypy.plugins.attrs as attrs_plugin
from mypy.plugin import Plugin

attrs_plugin.attr_attrib_makers.update({"flopy4.mf6.spec.field", "flopy4.mf6.spec.path"})


def plugin(version: str) -> type[Plugin]:
    return Plugin
