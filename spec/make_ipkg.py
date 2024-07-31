import argparse
import sys
import textwrap
from pathlib import Path
from pprint import pprint

import toml
from jinja2 import Template

PROJ_ROOT = Path(__file__).parents[1]
TOML_PATH = PROJ_ROOT / "spec" / "toml"
IPKG_PATH = PROJ_ROOT / "spec" / "ipkg"


class Toml2IPkg:
    """
    Verify MODFLOW 6 fortran source code format
    """

    def __init__(
        self,
        tomlfspec: str = None,
        outdir: str = None,
    ):
        """Toml2IPkg init"""

        self._tomlfspec = tomlfspec
        self._warnings = []

        tin = None
        tout = None

        with open(tomlfspec, "r") as fh:
            tin = toml.load(fh)
        with open(f"{PROJ_ROOT}/spec/mf6pkg.template") as f:
            tout = Template(f.read())

        if not (tin and tout):
            raise ValueError("FileSystem NO-OPT")

        jinja_blocks = []
        for b in tin["blocknames"]:
            unsupported = []

            for blkparam in tin["block"][b]:
                ptype = tin["block"][b][blkparam]["type"]
                if ptype.startswith("record"):
                    recparams = ptype.split()
                    recparams.remove(recparams[0])
                    typelist = []
                    for param in recparams:
                        t = tin["block"][b][param]["type"]
                        s = tin["block"][b][param]["shape"]
                        if t == "keyword":
                            typelist.append("MFKeyword()")
                        elif t == "string":
                            typelist.append("MFString()")
                        elif t == "integer":
                            if s == "":
                                typelist.append("MFInteger()")
                            else:
                                # todo add init args
                                typelist.append(f'MFArray(shape="{s}")')
                        elif t == "double":
                            if s == "":
                                typelist.append("MFDouble")
                            else:
                                # todo add init args
                                typelist.append(f'MFArray(shape="{s}")')
                        else:
                            raise ValueError(f"Cannot add record type => {t}")
                    tin["block"][b][blkparam]["rectypes"] = typelist
                elif ptype.startswith("recarray") or ptype.startswith(
                    "keystring"
                ):
                    unsupported.append(blkparam)

            jinja_d = {}
            jinja_d[b] = tin["block"][b].copy()
            for p in unsupported:
                del jinja_d[b][p]
                self._warnings.append(
                    f"Unsupported RECARRAY/KEYSTRING params removed: {p}"
                )
            jinja_blocks.append(jinja_d)

        comp = tin["component"].title()
        subcomp = tin["subcomponent"].title()
        fspec = f"{IPKG_PATH}/{comp.lower()}_{subcomp.lower()}.py"

        psource = tout.render(c=comp, s=subcomp, block_list=jinja_blocks)

        with open(fspec, "w") as f:
            f.write(psource)

    def warn(self):
        if len(self._warnings):
            print(f"TOML: {self._tomlfspec}")
            sys.stderr.write("Warnings:\n")
            for warn in self._warnings:
                sys.stderr.write("  " + warn + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Convert TOML files to FloPy package files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Generate FloPy package files from TOML files. This
            script converts TOML files to package specification
            files, each representing a parameter set for a
            particular input definition.
            """
        ),
    )
    parser.add_argument(
        "-t",
        "--toml",
        required=False,
        default=TOML_PATH,
        help="Path to a toml file or directory containing toml files",
    )
    parser.add_argument(
        "-o",
        "--outdir",
        required=False,
        default=IPKG_PATH,
        help="The directory to write Fortran source files",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        required=False,
        default=False,
        help="Whether to show verbose output",
    )
    args = parser.parse_args()
    outdir = Path(args.outdir) if args.outdir else Path.cwd()
    Path(outdir).mkdir(exist_ok=True)
    verbose = args.verbose

    tspec = Path(args.toml)
    tomls = []
    if tspec.is_dir():
        tomls = list(tspec.glob("**/*.toml"))
    elif tspec.suffix.lower() in [".toml"]:
        tomls = [tspec]

    assert all(
        p.is_file() for p in tomls
    ), f"TOMLs not found: {[p for p in tomls if not p.is_file()]}"

    if verbose:
        print("Converting TOMLs:")
        pprint(tomls)

    toml_d = {}
    for t in tomls:
        converter = Toml2IPkg(t, str(outdir))
        if verbose:
            converter.warn()

    if verbose:
        print("...done.")
