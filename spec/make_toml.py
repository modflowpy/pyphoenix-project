import argparse
import sys
import textwrap
from pathlib import Path
from pprint import pprint

import toml

MF6_LENVARNAME = 16
F90_LINELEN = 82
PROJ_ROOT = Path(__file__).parents[1]
DFN_PATH = PROJ_ROOT / "spec" / "dfn"
TOML_PATH = PROJ_ROOT / "spec" / "toml"

# parameter defaults
mf6_param_dfn = {
    "name": "",
    "type": "",
    "block_variable": False,
    "valid": [],
    "shape": "",
    "tagged": True,
    "in_record": False,
    "layered": False,
    "time_series": False,
    "reader": "",
    "optional": False,
    "preserve_case": False,
    "default_value": None,
    "numeric_index": False,
    "longname": "",
    "description": "",
    "deprecated": "",
}


class Dfn2Toml:
    """
    Verify MODFLOW 6 fortran source code format
    """

    def __init__(
        self,
        dfnfspec: str = None,
        outdir: str = None,
    ):
        """dfn2toml init"""

        self._dfnfspec = dfnfspec
        self._outdir = (Path(outdir),)
        self._var_d = {}
        self.component = ""
        self.subcomponent = ""
        self._warnings = []
        self._multi_package = False
        self._stress_package = False
        self._advanced_package = False
        self._subpackage = []

        self.component, self.subcomponent = self._dfnfspec.stem.upper().split(
            "-"
        )
        self._set_var_d()
        blocknames = self.get_blocknames()

        d = {
            "component": self.component,
            "subcomponent": self.subcomponent,
            "blocknames": blocknames,
            "multipkg": False,
            "stress": False,
            "advanced": False,
            # "subpackage": [],
            "block": {},
        }

        for b in blocknames:
            block_d = self._substitute(b, self.component, self.subcomponent)
            d["block"][b] = {}
            for p in block_d.keys():
                name = block_d[p]["name"]
                del block_d[p]["name"]
                d["block"][b][name] = block_d[p]

        if self._multi_package:
            d["multi"] = True
        if self._stress_package:
            d["stress"] = True
        if self._advanced_package:
            d["advanced"] = True
        # if len(self._subpackage) > 0:
        #    d["subpackage"] = self._subpackage.copy()

        fname = f"{self.component.lower()}-{self.subcomponent.lower()}.toml"
        fspec = self._outdir[0] / fname
        with open(
            fspec,
            "w",
        ) as fh:
            toml.dump(d, fh)

    def warn(self):
        if len(self._warnings):
            print(f"DFN: {self._dfnfspec}")
            sys.stderr.write("Warnings:\n")
            for warn in self._warnings:
                sys.stderr.write("  " + warn + "\n")

    def _set_var_d(self):
        f = open(self._dfnfspec, "r")
        lines = f.readlines()
        f.close()

        vardict = {}
        vd = {}

        for line in lines:
            # skip blank lines
            if len(line.strip()) == 0:
                if len(vd) > 0:
                    name = vd["name"]
                    if "block" in vd:
                        block = vd["block"]
                        key = (name, block)
                    else:
                        key = name
                    if name in vardict:
                        raise Exception(
                            "Variable already exists in dictionary: " + name
                        )
                    vardict[key] = vd
                vd = {}
                continue

            # parse comments for package scoped settings
            if "#" in line.strip()[0]:
                if "flopy multi-package" in line.strip():
                    self._multi_package = True
                elif "package-type" in line.strip():
                    pkg_tags = line.strip().split()
                    if pkg_tags[2] == "stress-package":
                        self._stress_package = True
                    if pkg_tags[2] == "advanced-stress-package":
                        self._stress_package = True
                        self._advanced_package = True
                elif "mf6 subpackage" in line.strip():
                    sp = line.replace("# mf6 subpackage ", "").strip()
                    sp = sp.upper()
                    self._subpackage.append(sp.ljust(16))
                continue

            ll = line.strip().split()
            if len(ll) > 1:
                k = ll[0]
                istart = line.index(" ")
                v = line[istart:].strip()
                if k in vd:
                    raise Exception(
                        "Attribute already exists in dictionary: " + k
                    )
                vd[k] = v

        if len(vd) > 0:
            name = vd["name"]
            if "block" in vd:
                block = vd["block"]
                key = (name, block)
            else:
                key = name
            if name in vardict:
                raise Exception(
                    "Variable already exists in dictionary: " + name
                )
            vardict[key] = vd

        self._var_d = vardict

    def _substitute(self, blockname, component, subcomponent):
        block_d = {}
        ra_d = {}
        for k in self._var_d:
            varname, block = k
            if block != blockname:
                continue

            v = self._var_d[k]

            for k in v.keys():
                if k.lower() not in mf6_param_dfn.keys():
                    if (
                        k.lower() != "block"
                        and k.lower() != "name"
                        and k.lower() != "mf6internal"
                    ):
                        self._warnings.append(
                            f"Warning unhandled key: {k.lower()}"
                        )

            if "block_variable" in v and v["block_variable"].upper() == "TRUE":
                continue

            vtype = v["type"].lower()
            if vtype == "double precision":
                vtype = "double"

            d = None
            d = mf6_param_dfn.copy()
            for k in mf6_param_dfn.keys():
                if k in v:
                    if isinstance(mf6_param_dfn[k], bool):
                        if v[k].lower() == "true":
                            d[k] = True
                        elif v[k].lower() == "false":
                            d[k] = False
                    elif k == "valid":
                        valid = v[k].strip().split()
                        if len(valid) > 0:
                            d[k] = valid.copy()
                    elif k == "type":
                        d[k] = vtype
                    elif k == "description":
                        d[k] = v[k].replace("\\", "").strip()
                    else:
                        d[k] = v[k]

            if d["type"].lower().startswith("recarray"):
                ra_d[varname] = d
            else:
                block_d[varname] = d

        bparams = {**block_d, **ra_d}
        return bparams

    def get_blocknames(self):
        blocknames = []
        for var, block in self._var_d:
            if block not in blocknames:
                blocknames.append(block.strip())
        return blocknames


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Convert DFN files to TOML files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Generate TOML from DFN files. This script converts
            definition (DFN) files to TOML specification files,
            each representing a parameter set for a particular
            input definition.
            """
        ),
    )
    parser.add_argument(
        "-d",
        "--dfn",
        required=False,
        default=DFN_PATH,
        help="Path to a DFN file or directory contiaining DFN files",
    )
    parser.add_argument(
        "-o",
        "--outdir",
        required=False,
        default=TOML_PATH,
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

    dfn = Path(args.dfn)
    dfns = []
    if dfn.is_dir():
        dfns = list(dfn.glob("**/*.dfn"))
    elif dfn.suffix.lower() in [".dfn"]:
        dfns = [dfn]

    assert all(
        p.is_file() for p in dfns
    ), f"DFNs not found: {[p for p in dfns if not p.is_file()]}"

    if verbose:
        print("Converting DFNs:")
        pprint(dfns)

    dfn_d = {}
    for dfn in dfns:
        converter = Dfn2Toml(dfn, str(outdir))
        if verbose:
            converter.warn()

    if verbose:
        print("...done.")
