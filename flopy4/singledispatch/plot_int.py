from typing import Any

from flopy4.singledispatch.plot import plot


@plot.register
def _(v: int, **kwargs) -> Any:
    print(f"Plotting a model with kwargs: {kwargs}")
    return v
