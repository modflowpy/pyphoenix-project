"""How the converter finds a component's blocks and fields, all from its class
(see `flopy4.mf6.spec`). The classes are the only schema the runtime reads, so
the last test holds them to the DFNs they're generated from."""

import importlib.util
import sys
from pathlib import Path

import pytest
from modflow_devtools.dfns import LocalDfnRegistry
from modflow_devtools.dfns.schema import File, Keyword, Record, _is_dynamic_key, _leading_tags
from modflow_devtools.dfns.schema import List as ListField

from flopy4.mf6 import spec
from flopy4.mf6.component import FNAMES
from flopy4.mf6.gwf.chd import Chd
from flopy4.mf6.gwf.evt import Evt
from flopy4.mf6.gwf.lak import Lak
from flopy4.mf6.gwf.oc import Oc
from flopy4.mf6.gwf.rcha import Rcha
from flopy4.mf6.gwf.sto import Sto
from flopy4.mf6.prt.prp import Prp
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.codegen import filters
from flopy4.mf6.utils.codegen.make import make_modules
from flopy4.mf6.utl.tas import Tas
from flopy4.mf6.utl.ts import Ts


def _names(fields) -> list[str]:
    return [f.name for f in fields]


def test_blocks_in_file_order():
    assert list(spec.file_blocks(Chd)) == ["options", "dimensions", "period"]
    # DIMENSIONS holds only the computed MAXBOUND
    assert spec.file_blocks(Chd)["dimensions"] == []
    assert spec.block_keys(Chd, "dimensions").computed == ("maxbound",)
    # MAXBOUND's beside a stored dimension
    assert _names(spec.file_blocks(Evt)["dimensions"]) == ["nseg"]
    assert spec.block_keys(Evt, "dimensions").computed == ("maxbound",)
    assert spec.block_keys(Evt, "options").computed == ()


def test_shared_keyword():
    head = spec.block_keys(Oc, "options").tagged["head"]
    assert _names(head) == ["head_file", "headprint"]
    assert [spec.following_tags(f) for f in head] == [["fileout"], ["print_format"]]
    # no clash between a record and another field: TS's SFAC and SFACS
    sfac = spec.block_keys(Ts, "attributes").tagged
    assert _names(sfac["sfac"]) == ["sfacrecord_single"]
    assert _names(sfac["sfacs"]) == ["sfac"]


def test_alias():
    tagged = spec.block_keys(Ts, "attributes").tagged
    assert tagged["names"] == tagged["name"]


def test_untagged():
    assert spec.block_keys(Chd, "period").untagged.name == "_stress_period_data"
    assert spec.block_keys(Sto, "period").untagged.name == "stress_period_data"
    assert spec.block_keys(Tas, "time").untagged.name == "tas_array"
    # rows that lead with a value, whatever keyword follows it
    lak = spec.block_keys(Lak, "period")
    assert lak.untagged.name == "_stress_period_data"
    assert not lak.tagged


def test_tagged_lists():
    period = spec.block_keys(Oc, "period")
    assert period.untagged is None
    assert set(period.tagged) == {"save", "print"}
    # a union's items and its plain words
    period = spec.block_keys(Prp, "period")
    assert {"first", "all", "last", "frequency", "steps"} <= set(period.tagged)


def test_dynamic_keys():
    period = spec.block_keys(Rcha, "period")
    assert {path: f.name for path, f in period.dynamic.items()} == {"options.auxiliary": "aux"}
    assert set(period.tagged) == {"irch", "recharge"}
    assert period.untagged is None


def test_binding_rows_arent_keyed():
    group = spec.block_keys(Simulation, "solutiongroup")
    assert group.untagged is None
    assert set(group.tagged) == {"mxiter"}
    assert "solutiongroup" in spec.binding_fields(Simulation)


@pytest.fixture(scope="module")
def generated(dfn_path, tmp_path_factory):
    """Each component's DFN, with the class generated from it: by the DFNs
    at hand, so this holds whichever the tests are given."""
    dfns = LocalDfnRegistry(path=dfn_path).spec(schema_version="2.0.0.dev3").components
    specs = make_modules(dfns=dfns, outdir=tmp_path_factory.mktemp("routing"), makedirs=True)
    registered = dict(FNAMES)
    loaded = []
    out = []
    for s in specs:
        path = Path(s.outpath)
        if path.name == "__init__.py" or s.dfn_name not in dfns:
            continue
        name = f"_routing_{s.dfn_name.replace('-', '_')}"
        module_spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[name] = module
        loaded.append(name)
        module_spec.loader.exec_module(module)
        out.append((dfns[s.dfn_name], getattr(module, s.class_name)))
    yield out
    FNAMES.clear()
    FNAMES.update(registered)
    for name in loaded:
        del sys.modules[name]


def _following_dfn(f) -> list[str]:
    """What follows a DFN field's leading keyword, for the rows the converter
    has to tell apart."""
    if not isinstance(f, Record):
        return []
    members = list(f.fields.values())
    if len(members) < 2:
        return []
    second = members[1]
    if isinstance(second, Keyword):
        return [t.lower() for t in [second.name, *second.aliases]]
    if isinstance(second, File) and second.mode_keyword and second.direction:
        return [f"file{second.direction}"]
    return []


def test_classes_route_as_their_dfns(generated):
    """What the converter reads from a class is what its DFN says: its blocks
    in order, each block's keys in order, its untagged and dynamic fields, and
    its repeating blocks' headers."""
    assert generated
    problems = []
    for component, cls in generated:
        blocks = spec.file_blocks(cls)
        order = [b for b in component.blocks or {} if b in blocks]
        if order != list(blocks):
            problems.append((component.name, "order", list(blocks), order))
        for name in blocks:
            where = (component.name, name)
            block = component.blocks.get(name)
            if block is None:
                problems.append((*where, "not in the DFN"))
                continue
            keys = spec.block_keys(cls, name)
            fields = [f for b, f in filters.flat_fields(component) if b == name]
            binding = name in spec.binding_fields(cls)

            # a field's own keys (a union's arms) can come in any order
            words = [
                t.lower() for f in fields if not _is_dynamic(f) for t in sorted(_leading_tags(f))
            ]
            have = list(keys.computed)
            for a in blocks[name]:
                keyed = spec.is_tagged(a) and a not in keys.dynamic.values()
                if keyed and not a.metadata.get("row"):
                    have += sorted(spec.leading_tags(a))
            words, have = list(dict.fromkeys(words)), list(dict.fromkeys(have))
            if words != have:
                problems.append((*where, "keys", have, words))
            for word, shared in keys.tagged.items():
                if len(shared) > 1:
                    dfn_shared = [f for f in fields if word in map(str.lower, _leading_tags(f))]
                    want = [_following_dfn(f) for f in dfn_shared]
                    if [spec.following_tags(a) for a in shared] != want:
                        problems.append((*where, "following", word))

            untagged = [f for f in fields if not getattr(f, "tagged", True)]
            if binding:
                untagged = []
            if (keys.untagged is None) != (not untagged):
                problems.append((*where, "untagged", keys.untagged, _names(untagged)))
            dynamic = {
                next(iter(_record(f).fields.values())).fk.path for f in fields if _is_dynamic(f)
            }
            if set(keys.dynamic) != dynamic:
                problems.append((*where, "dynamic", set(keys.dynamic), dynamic))

            if block.header is None:
                if name in cls.headers:
                    problems.append((*where, "header not in the DFN"))
                continue
            header = cls.headers[name]
            kind = block.header.field.type
            if header.kind != kind or header.index != bool(getattr(block.header.field, "index", 0)):
                problems.append((*where, "header", header, kind))
            filled = any(a.metadata.get("fill_forward") for a in blocks[name])
            if filled != bool(block.header.fill_forward):
                problems.append((*where, "fill_forward", filled))
        if spec.computed_fields(cls):
            dims = component.blocks["dimensions"].fields
            if next(iter(dims)) != "maxbound":
                problems.append((component.name, "maxbound isn't first", list(dims)))
    assert problems == []


def _record(f):
    return f.item if isinstance(f, ListField) else f


def _is_dynamic(f) -> bool:
    record = _record(f)
    if not isinstance(record, Record):
        return False
    return _is_dynamic_key(next(iter(record.fields.values()), None))
