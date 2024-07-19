from collections.abc import MutableMapping
from typing import Any, Dict

from flopy4.parameter import MFParameter, MFParameters
from flopy4.utils import strip


def get_member_params(cls) -> Dict[str, MFParameter]:
    if not issubclass(cls, MFBlock):
        raise ValueError(f"Expected MFBlock, got {cls}")

    return {
        k: v
        for k, v in cls.__dict__.items()
        if issubclass(type(v), MFParameter)
    }


class MFBlock(MutableMapping):
    def __init__(self, name=None, index=None, *args, **kwargs):
        self.name = name
        self.index = index
        self.params = MFParameters()
        self.update(dict(*args, **kwargs))
        for key, param in self.items():
            setattr(self, key, param)

    def __getattribute__(self, name: str) -> Any:
        attr = super().__getattribute__(name)
        if isinstance(attr, MFParameter):
            # shortcut to parameter value for instance attributes.
            # the class attribute is the full param specification.
            return attr.value
        else:
            return attr

    def __getitem__(self, key):
        return self.params[key]

    def __setitem__(self, key, value):
        self.params[key] = value

    def __delitem__(self, key):
        del self.params[key]

    def __iter__(self):
        return iter(self.params)

    def __len__(self):
        return len(self.params)

    @classmethod
    def load(cls, f, strict=False):
        name = None
        index = None
        found = False
        params = dict()
        members = get_member_params(cls)

        while True:
            pos = f.tell()
            line = strip(f.readline()).lower()
            words = line.split()
            key = words[0]
            if key == "begin":
                found = True
                name = words[1]
                if len(words) > 2 and str.isdigit(words[2]):
                    index = words[2]
            elif key == "end":
                break
            elif found:
                if not strict or key in members:
                    f.seek(pos)
                    param = members[key]
                    param.block = name
                    params[key] = type(param).load(f, spec=param)

        return cls(name, index, **params)

    def write(self, f):
        index = self.index if self.index is not None else ""
        begin = f"BEGIN {self.name.upper()} {index}\n"
        end = f"END {self.name.upper()}\n"

        f.write(begin)
        for param in self.values():
            param.write(f)
        f.write(end)


class MFBlocks:
    pass
