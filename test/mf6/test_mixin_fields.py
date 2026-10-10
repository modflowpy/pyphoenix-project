from importlib import import_module
from typing import Optional

import attrs
import pytest

from flopy4.mf6._mixin_fields import find_mixin_gaps, mixin_chains, mixin_gaps
from flopy4.mf6._sync import _MF6_ROOT, _generated_files, _module_name
from flopy4.mf6.dis_methods import DisMethods
from flopy4.mf6.gwf_methods import GwfMethods
from flopy4.mf6.tdis_methods import TdisMethods
from flopy4.mf6.utils.codegen.make import MIXINS
from flopy4.mf6.utl.ts_methods import TsMethods


def _read(mixin: type, method: str) -> set[str]:
    return {".".join(c) for c in mixin_chains(mixin)[f"{mixin.__name__}.{method}"]}


@pytest.mark.parametrize(
    "mixin,method,reads,skips",
    [
        # through a nested helper's parent, and a child field
        (GwfMethods, "Output.head", {"oc.head_file", "netcdf_mesh2d_file"}, set()),
        # through a local name, but not getattr with a default
        (GwfMethods, "Output._grb_path", {"dis", "dis.path"}, {"dis.grb_file"}),
        # a dict with literal keys passed as **kwargs
        (DisMethods, "from_grid", {"crs", "nlay", "delr"}, set()),
        # a comprehension's variable, over `self.x or []`
        (TdisMethods, "to_time", {"perioddata.perlen", "perioddata.nstp"}, set()),
        # an inner class's keyword arguments
        (TsMethods, "from_series", {"Timeseries.ts_time", "sfacrecord_single"}, set()),
    ],
)
def test_mixin_chains(mixin, method, reads, skips):
    read = _read(mixin, method)
    assert reads <= read
    assert not skips & read


def test_checked_in_classes_have_no_gaps():
    modules = [import_module(_module_name(rel)) for rel in sorted(_generated_files(_MF6_ROOT))]
    mixins = {
        getattr(import_module(module), cls)
        for ms in MIXINS.values()
        for module, _, cls in (m.partition(":") for m in ms)
    }
    assert find_mixin_gaps(modules, mixins) == []


class _Methods:
    def size(self):
        return self.n * len(self.child.items or [])

    @classmethod
    def build(cls):
        return cls(n=1, child=cls.Child(items=[]))

    def optional(self):
        return getattr(self, "absent", None)


@attrs.define
class _Child:
    items: Optional[list[int]] = None


@attrs.define
class _Whole(_Methods):
    Child = _Child
    n: int = 0
    child: Optional[_Child] = None


@attrs.define
class _ChildLacking:
    other: int = 0


@attrs.define
class _Lacking(_Methods):
    Child = _ChildLacking
    child: Optional[_ChildLacking] = None


def test_mixin_gaps():
    assert mixin_gaps(_Whole, _Methods) == []
    assert mixin_gaps(_Lacking, _Methods) == [
        "_Methods.size: no _ChildLacking.items, _Lacking.n",
        "_Methods.build: no _ChildLacking.items, _Lacking.n",
    ]
