from types import MappingProxyType
from typing import Any, Dict, Optional


class ResolveSingleton(object):
    def __new__(
        cls,
        name: Optional[str] = "sim",
        models: Optional[Dict[str, Dict]] = None,
    ):
        if not hasattr(cls, "instance"):
            cls.instance = super(ResolveSingleton, cls).__new__(cls)
            cls.instance.name = name
            cls.instance.models = MappingProxyType(models)
        return cls.instance


class Resolve:
    def __init__(
        self,
        name: Optional[str] = "sim",
        models: Optional[Dict[str, Dict]] = None,
    ):
        ResolveSingleton(name, models)

    def resolve(self, mempath: str) -> Any:
        res = None
        resolver = ResolveSingleton()
        words = mempath.split("/")
        sim_name = words.pop(0)
        assert sim_name == resolver.name
        cmp_name = words.pop(0)
        if cmp_name in list(resolver.models):
            res = resolver.models[cmp_name].value
        # elif cmp_name in list(resolver.exchanges):
        #    res = resolver.exchanges[cmp_name].value
        for i in range(len(words)):
            if res is None:
                break
            res = res.get(words[i], None)
        return res
