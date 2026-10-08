"""flopy4.mypy_plugin lets mypy read the converters of generated fields."""

import pytest

api = pytest.importorskip("mypy.api")

SNIPPET = """
from flopy4.mf6.gwf import Chd, Gwf, Npf, Oc

Gwf(newtonoptions=True)
Npf(xt3doptions=True, rewet=(1.0, 1, 0))
Oc(budget_file="x.cbc", headprint="COLUMNS 10 WIDTH 12 DIGITS 6 GENERAL")
Chd(auxiliary="conc")
Oc(budget_file=1)
reveal_type(Npf().rewet)
reveal_type(Oc().budget_file)
"""


def _mypy(tmp_path) -> list[str]:
    (tmp_path / "snippet.py").write_text(SNIPPET)
    config = tmp_path / "mypy.ini"
    config.write_text(
        "[mypy]\nignore_missing_imports = True\nfollow_imports = silent\n"
        "plugins = flopy4.mypy_plugin\n"
    )
    out, _, _ = api.run(
        [
            "--config-file",
            str(config),
            "--cache-dir",
            str(tmp_path / ".mypy_cache"),
            str(tmp_path / "snippet.py"),
        ]
    )
    return [line.split(": ", 1)[1] for line in out.splitlines() if "snippet.py:" in line]


@pytest.mark.slow
def test_plugin_reads_converters(tmp_path):
    lines = _mypy(tmp_path)
    errors = [line for line in lines if line.startswith("error")]
    # only the int for a path is rejected
    assert len(errors) == 1 and '"budget_file"' in errors[0] and '"int"' in errors[0]
    # reads keep the field's type
    assert 'Revealed type is "flopy4.mf6.gwf.npf.Npf.Rewet | None"' in "\n".join(lines)
    assert 'Revealed type is "pathlib.Path | None"' in "\n".join(lines)
