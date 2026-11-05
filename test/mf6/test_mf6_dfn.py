"""The DFNs sync stores with the classes, and what the converter reads from
them: each class's DFN, the attribute holding each DFN field, and how a
block's rows find their fields. These read the stored DFNs, not the ones
CI downloads, so they hold for the classes as generated."""

import importlib

import pytest

from flopy4.mf6 import spec
from flopy4.mf6.gwf.chd import Chd
from flopy4.mf6.gwf.oc import Oc
from flopy4.mf6.gwf.rcha import Rcha
from flopy4.mf6.gwf.sto import Sto
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.codegen import filters
from flopy4.mf6.utils.codegen.make import _component_module
from flopy4.mf6.utl.tas import Tas
from flopy4.mf6.utl.ts import Ts


def _classes():
    for name in spec._dfns():
        try:
            module = importlib.import_module(_component_module(name))
        except ImportError:
            continue
        if (cls := getattr(module, filters.class_name(name), None)) is not None:
            yield name, cls


CLASSES = dict(_classes())


def test_stored_dfns_cover_classes():
    assert CLASSES
    for name, cls in CLASSES.items():
        assert spec.dfn(cls).name == name == cls.dfn_name


@pytest.fixture(scope="module")
def whole_set():
    """The stored DFNs as devtools loads them, all at once, checking the
    relations between them, which the converter's lazy loads skip."""
    from modflow_devtools.dfns import LocalDfnRegistry

    from flopy4.mf6._sync import _DFN_SCHEMA_VERSION

    registry = LocalDfnRegistry(path=spec._stored_dfns())
    return registry.spec(schema_version=_DFN_SCHEMA_VERSION).components


def test_lazy_dfns_match_whole_set(whole_set):
    """Each DFN loaded alone is the one devtools loads in the whole set,
    and its header has the same top-level keys."""
    stored = spec._dfns()
    assert sorted(stored) == sorted(whole_set)
    for name, component in whole_set.items():
        assert stored[name] == component, name
        header = stored.headers[name]
        for key in spec.DfnHeader._fields:
            # only packages have multi
            default = False if key == "multi" else None
            assert getattr(header, key) == getattr(component, key, default), (name, key)


@pytest.mark.parametrize("name", sorted(CLASSES))
def test_attr_names_from_headers(name, whole_set):
    """Codegen names the same attributes resolving links by the lazy
    loader's headers as by the whole set."""
    from flopy4.mf6.utils.codegen.make import attr_names

    cls = CLASSES[name]
    assert spec.attr_names(cls) == attr_names(whole_set[name], whole_set)


@pytest.mark.parametrize("name", sorted(CLASSES))
def test_attr_names(name):
    """Every DFN field codegen made an attribute for maps to it, and every
    attribute holds a DFN field, except a model's package slots (one per
    package type, all from the name file's package list)."""
    cls = CLASSES[name]
    names = spec.attr_names(cls)
    fields = spec.fields_dict(cls)
    for key, attr in names.items():
        assert attr in fields or isinstance(getattr(cls, attr, None), property), key
    unmapped = {a for a, f in fields.items() if a not in names.values()}
    if filters.is_model_nam(name):
        assert all(fields[a].metadata["block"] == "packages" for a in unmapped)
    else:
        assert not unmapped


@pytest.mark.parametrize("name", sorted(CLASSES))
def test_block_keys(name):
    """A block's untagged field, if any, is its last; a keyword leading
    more than one field's rows is told apart by the next one."""
    cls = CLASSES[name]
    for block in spec.dfn(cls).blocks or {}:
        keys = spec.block_keys(cls, block)
        fields = [f for b, f in filters.flat_fields(spec.dfn(cls)) if b == block]
        if keys.untagged is not None:
            assert fields[-1] is keys.untagged, block
            assert sum(not getattr(f, "tagged", True) for f in fields) == 1, block
        for tag, shared in keys.tagged.items():
            if len(shared) > 1:
                following = [tuple(spec.following_tags(f)) for f in shared]
                assert all(following) and len(set(following)) == len(following), (block, tag)


@pytest.mark.parametrize("name", sorted(CLASSES))
def test_block_order(name):
    """Options, then dimensions, come before every other block, so a load
    reading blocks in DFN order has the auxiliary names, switches and
    sizes before the blocks read by them."""
    blocks = list(spec.dfn(CLASSES[name]).blocks or {})
    first = [b for b in ("options", "dimensions") if b in blocks]
    assert blocks[: len(first)] == first


def test_attr_names_examples():
    assert spec.attr_names(Oc)[("options", "head_filerecord")] == "head_file"
    assert spec.attr_names(Oc)[("options", "headprintrecord")] == "headprint"
    assert spec.attr_names(Oc)[("period", "stress_period_data")] == "_period_data"
    assert spec.attr_names(Chd)[("options", "ts_filerecord")] == "ts"
    assert spec.attr_names(Chd)[("dimensions", "maxbound")] == "maxbound"
    assert spec.attr_names(Sto)[("period", "stress_period_data")] == "period_data"
    assert spec.attr_names(Rcha)[("period", "aux")] == "aux"
    assert spec.attr_names(Tas)[("time", "tas_array")] == "tas_array"
    assert spec.attr_names(Simulation)[("solutiongroup", "solutiongroup")] == "solutiongroup"


def test_shared_keyword():
    head = spec.block_keys(Oc, "options").tagged["head"]
    assert [f.name for f in head] == ["head_filerecord", "headprintrecord"]
    assert [spec.following_tags(f) for f in head] == [["fileout"], ["print_format"]]
    # no clash between a record and another field: TS's SFAC and SFACS
    sfac = spec.block_keys(Ts, "attributes").tagged
    assert [f.name for f in sfac["sfac"]] == ["sfacrecord_single"]
    assert [f.name for f in sfac["sfacs"]] == ["sfacrecord"]


def test_headers_and_untagged():
    dfn = spec.dfn(Simulation)
    assert dfn.blocks["solutiongroup"].header.field.name == "group_num"
    group = spec.block_keys(Simulation, "solutiongroup")
    assert group.untagged.name == "solutiongroup"
    assert set(group.tagged) == {"mxiter"}
    assert spec.dfn(Tas).blocks["time"].header.field.type == "double"
    assert spec.block_keys(Tas, "time").untagged.name == "tas_array"
    period = spec.block_keys(Oc, "period")
    assert spec.dfn(Oc).blocks["period"].header.fill_forward
    assert period.untagged is None  # OC's output is a tagged list
    assert set(period.tagged) == {"save", "print"}


def test_dynamic_keys():
    period = spec.block_keys(Rcha, "period")
    assert {path: f.name for path, f in period.dynamic.items()} == {"options.auxiliary": "aux"}
    assert set(period.tagged) == {"irch", "recharge"}
    assert period.untagged is None
