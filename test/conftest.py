from pathlib import Path

PROJ_ROOT_PATH = Path(__file__).parents[1]
DOCS_PATH = PROJ_ROOT_PATH / "docs"
EXAMPLES_PATH = DOCS_PATH / "examples"
EXCLUDED_EXAMPLES = []


def pytest_generate_tests(metafunc):
    if "example_script" in metafunc.fixturenames:
        scripts = {
            file.name: file
            for file in sorted(EXAMPLES_PATH.glob("*example.py"))
            if file.stem not in EXCLUDED_EXAMPLES
        }
        metafunc.parametrize(
            "example_script", scripts.values(), ids=scripts.keys()
        )
