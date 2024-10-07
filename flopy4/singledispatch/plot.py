from functools import singledispatch
from typing import Any


@singledispatch
def plot(obj, **kwargs) -> Any:
    raise NotImplementedError(
        "plot method not implemented for type {}".format(type(obj))
    )
