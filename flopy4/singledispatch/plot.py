from functools import singledispatch


@singledispatch
def plot(obj, **kwargs):
    raise NotImplementedError(
        "plot method not implemented for type {}".format(type(obj))
    )
