import ast
import inspect
import subprocess
import sys
from importlib.metadata import entry_points

import pytest

from flopy4.singledispatch.plot import plot


def get_function_body(func):
    source = inspect.getsource(func)
    parsed = ast.parse(source)
    for node in ast.walk(parsed):
        if isinstance(node, ast.FunctionDef):
            return ast.get_source_segment(source, node.body[0])
    raise ValueError("Function body not found")


def run_test_in_subprocess(test_func):
    def wrapper():
        test_func_source = get_function_body(test_func)
        test_code = f"""
import pytest
from importlib.metadata import entry_points
from flopy4.singledispatch.plot import plot

{test_func_source}

"""
        result = subprocess.run(
            [sys.executable, "-c", test_code], capture_output=True, text=True
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr)
        assert result.returncode == 0, f"Test failed: {test_func.__name__}"

    return wrapper


@run_test_in_subprocess
def test_register_singledispatch_with_entrypoints():
    eps = entry_points(group="flopy4", name="plot")
    for ep in eps:
        ep.load()

    # should not throw an error, because plot_int was loaded via entry points
    return_val = plot(5)
    assert return_val == 5
    with pytest.raises(NotImplementedError):
        plot("five")


@run_test_in_subprocess
def test_register_singledispatch_without_entrypoints():
    # should throw an error, because plot_int was not loaded via entry points
    with pytest.raises(NotImplementedError):
        plot(5)
    with pytest.raises(NotImplementedError):
        plot("five")
