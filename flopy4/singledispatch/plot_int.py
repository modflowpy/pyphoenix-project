from flopy4.singledispatch.plot import plot


@plot.register
def _(v: int, **kwargs):
    print(f"Plotting a model with kwargs: {kwargs}")
