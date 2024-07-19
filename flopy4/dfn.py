from pathlib import Path

import toml


class Dfn:
    def __init__(self, component, subcomponent, dfn, *args, **kwargs):
        self._component = component
        self._subcomponent = subcomponent
        self._dfn = dfn

    def __getitem__(self, key):
        return self._dfn["block"][key]

    def __setitem__(self, key, value):
        self._dfn["block"][key] = value

    def __delitem__(self, key):
        del self._dfn["block"][key]

    def __iter__(self):
        return iter(self._dfn["block"])

    def __len__(self):
        return len(self._dfn["block"])

    @property
    def component(self):
        return self._component

    @property
    def subcomponent(self):
        return self._subcomponent

    @property
    def blocknames(self):
        return self._dfn["blocknames"]

    @property
    def dfn(self):
        return self._dfn

    def blocktags(self, blockname) -> list:
        return list(self._dfn["block"][blockname])

    def block(self, blockname) -> dict:
        return self._dfn["block"][blockname]

    def param(self, blockname, tagname) -> dict:
        return self._dfn["block"][blockname][tagname]

    @classmethod
    def load(cls, f, metadata=None):
        p = Path(f)

        if not p.exists():
            raise ValueError("Invalid DFN path")

        component, subcomponent = p.stem.split("-")
        data = toml.load(f)

        return cls(component, subcomponent, data, **metadata)


class DfnSet:
    def __init__(self, *args, **kwargs):
        self._dfns = dict()

    def __getitem__(self, key):
        return self._dfns[key]

    def __setitem__(self, key, value):
        self._dfns[key] = value

    def __delitem__(self, key):
        del self._dfns[key]

    def __iter__(self):
        return iter(self._dfns)

    def __len__(self):
        return len(self._dfns)

    def add(self, key, dfn):
        if key in self._dfns:
            raise ValueError("DFN exists in container")

        self._dfns[key] = dfn

    def get(self, key):
        if key not in self._dfns:
            raise ValueError("DFN does not exist in container")

        return self._dfns[key]

    #def get(self, component, subcomponent):
    #    key = f"{component.lower()}-{subcomponent.lower()}"
    #    if key not in self._dfns:
    #        raise ValueError("DFN does not exist in container")
    #
    #    return self._dfns[key]
