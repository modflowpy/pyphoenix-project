import math
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pytest
from attrs import asdict, astuple
from numpy.typing import NDArray

from flopy4.attrs import (
    context,
    is_frozen,
    param,
    params,
)

# Records are product types: named, ordered tuples of scalars.
# Records are immutable: they can't be changed, only evolved.


@context(frozen=True)
class Record:
    rb: bool = param(description="bool in record")
    ri: int = param(description="int in record")
    rf: float = param(description="float in record")
    rs: Optional[str] = param(
        description="optional str in record", default=None
    )


@context
class Block:
    b: bool = param(description="bool")
    i: int = param(description="int")
    f: float = param(description="float")
    s: str = param(description="str", optional=False)
    p: Path = param(description="path", optional=False)
    a: NDArray[np.int_] = param(description="array")
    r: Record = param(
        description="record",
        optional=False,
    )


# Keystrings are sum types: discriminated unions of records.


def test_spec():
    spec = params(Record)
    assert len(spec) == 4
    assert isinstance(spec, Dict)
    assert is_frozen(Record)

    spec = params(Block)
    assert len(spec) == 7
    assert isinstance(spec, Dict)
    assert not is_frozen(Block)

    b = spec["b"]
    assert b.type is bool
    assert b.metadata["description"] == "bool"

    i = spec["i"]
    assert i.type is int
    assert i.metadata["description"] == "int"

    f = spec["f"]
    assert f.type is float
    assert f.metadata["description"] == "float"

    s = spec["s"]
    assert s.type is str
    assert s.metadata["description"] == "str"

    p = spec["p"]
    assert p.type is Path
    assert p.metadata["description"] == "path"

    a = spec["a"]
    assert a.type == NDArray[np.int_]
    assert a.metadata["description"] == "array"

    r = spec["r"]
    assert r.type is Record
    assert r.metadata["description"] == "record"


def test_usage():
    r = Record(rb=True, ri=42, rf=math.pi)
    assert astuple(r) == (True, 42, math.pi, None)
    assert asdict(r) == {"rb": True, "ri": 42, "rf": math.pi, "rs": None}
    with pytest.raises(TypeError):
        # non-optional members are required
        Record(rb=True)
