from importlib.metadata import entry_points

from flopy4.singledispatch.plot import plot


def test_register_singledispatch_with_entrypoints():
    eps = entry_points(group="flopy4", name="plot")
    for ep in eps:
        _ = ep.load()

    # should not throw an error, because plot_int was loaded via entry points
    plot(5)
