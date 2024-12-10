import argparse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from flopy.utils import import_optional_dependency

from flopy4.dfn import Dfn

SPEC_PATH = Path(__file__).parent
DFN_PATH = SPEC_PATH / "dfn"
TOML_PATH = SPEC_PATH / "toml"


class Shim:
    @staticmethod
    def _attach_children(d: Any):
        if isinstance(d, Mapping):
            if "children" in d:
                for n, c in d["children"].items():
                    d[n] = c
                del d["children"]
            d = {k: Shim._attach_children(v) for k, v in d.items()}
        return d

    @staticmethod
    def _drop_empty(d: Any):
        if isinstance(d, Mapping):
            return {
                k: Shim._drop_empty(v)
                for k, v in d.items()
                if (v or isinstance(v, bool))
            }
        else:
            return d

    @staticmethod
    def _trim(d: dict) -> dict:
        del d["dfn"]
        del d["foreign_keys"]
        d["name"] = str(d["name"])
        return d

    @staticmethod
    def apply(d: dict) -> dict:
        return Shim._attach_children(Shim._drop_empty(Shim._trim(d)))


if __name__ == "__main__":
    """Convert DFN files to TOML."""

    tomlkit = import_optional_dependency("tomlkit")
    parser = argparse.ArgumentParser(description="Convert DFN files to TOML.")
    parser.add_argument(
        "--dfndir",
        type=str,
        default=DFN_PATH,
        help="Directory containing DFN files.",
    )
    parser.add_argument(
        "--outdir",
        default=TOML_PATH,
        help="Output directory.",
    )
    args = parser.parse_args()
    dfndir = Path(args.dfndir)
    outdir = Path(args.outdir)
    outdir.mkdir(exist_ok=True, parents=True)
    for dfn in Dfn.load_all(dfndir).values():
        with open(Path(outdir) / f"{dfn['name']}.toml", "w") as f:
            tomlkit.dump(Shim.apply(dfn), f)
