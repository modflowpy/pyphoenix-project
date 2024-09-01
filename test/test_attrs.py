from pathlib import Path
from typing import List

from flopy4.attrs import Array, context, param, params

# Records are product types: named, ordered tuples of scalars.
# Records are immutable: they can't be changed, only evolved.


@context(frozen=True)
class Record:
    rk: bool = param(description="keyword in record")
    ri: int = param(description="int in record")
    rd: float = param(description="double in record")


@context
class Block:
    k: bool = param(description="keyword")
    i: int = param(description="int")
    d: float = param(description="double")
    s: str = param(description="string", optional=False)
    f: Path = param(description="filename", optional=False)
    a: Array = param(description="array")
    r: Record = param(
        description="record",
        optional=False,
    )


# Keystrings are sum types: discriminated unions of records.


@context(frozen=True)
class All:
    all: bool = param(
        description="keyword to indicate save for all time steps in period."
    )


@context(frozen=True)
class First:
    first: bool = param(
        description="keyword to indicate save for first step in period."
    )


@context(frozen=True)
class Last:
    last: bool = param(
        description="keyword to indicate save for last step in period."
    )


@context(frozen=True)
class Frequency:
    frequency: int = param(
        description="save at the specified time step frequency."
    )


@context(frozen=True)
class Steps:
    steps: List[int] = param(description="save for each step specified.")


OCSetting = All | First | Last | Frequency | Steps


@context(multi=True)
class Period:
    ocsetting: OCSetting = param(
        description="keystring",
        optional=False,
    )


def test_introspection():
    spec = params(Block)
    print(spec)

    assert len(spec) == 7

    k = spec["k"]
    assert k.type is bool
    assert k.metadata["description"] == "keyword"

    i = spec["i"]
    assert i.type is int
    assert i.metadata["description"] == "int"

    d = spec["d"]
    assert d.type is float
    assert d.metadata["description"] == "double"

    s = spec["s"]
    assert s.type is str
    assert s.metadata["description"] == "string"

    f = spec["f"]
    assert f.type is Path
    assert f.metadata["description"] == "filename"

    a = spec["a"]
    assert a.type is Array
    assert a.metadata["description"] == "array"

    r = spec["r"]
    assert r.type is Record
    assert r.metadata["description"] == "record"

    spec = params(Period)
    assert len(spec) == 2

    index = spec["index"]
    assert index.type is int

    ocsetting = spec["ocsetting"]
    assert ocsetting.type is OCSetting
