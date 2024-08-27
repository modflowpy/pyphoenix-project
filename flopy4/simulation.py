from pathlib import Path
from typing import Dict, Optional

from flopy4.block import MFBlock
from flopy4.ispec.exg_gwfgwf import ExgGwfgwf
from flopy4.ispec.gwe_model import GweModel
from flopy4.ispec.gwf_model import GwfModel
from flopy4.ispec.gwt_model import GwtModel
from flopy4.ispec.prt_model import PrtModel
from flopy4.ispec.sim_nam import SimNam
from flopy4.ispec.sim_tdis import SimTdis
from flopy4.ispec.sln_ims import SlnIms
from flopy4.model import MFModel
from flopy4.package import MFPackage
from flopy4.resolver import Resolve


class MFSimulation:
    """
    MF6 simulation.
    """

    def __init__(
        self,
        name: Optional[str] = "sim",
        tdis: Optional[MFPackage] = None,
        models: Optional[Dict[str, MFModel]] = {},
        exchanges: Optional[Dict[str, Dict]] = {},
        solvers: Optional[Dict[str, Dict]] = {},
        nam: Optional[Dict[str, Dict]] = {},
    ):
        self.name = name
        self.mempath = name
        self.tdis = tdis
        self.models = models
        self.exchanges = exchanges
        self.solvers = solvers
        self.nam = nam

        self._resolv = Resolve(name=name, models=models)

    @classmethod
    def load(cls, f, **kwargs):
        """Load mfsim.nam from file."""
        models = dict()
        exchanges = dict()
        solvers = dict()
        sim_name = "sim"
        mempath = sim_name

        kwargs["mempath"] = f"{mempath}"
        kwargs["ftype"] = "nam6"

        nam = SimNam.load(f, **kwargs)

        tdis = MFSimulation.load_tdis(nam, **kwargs)
        MFSimulation.load_models(nam, models, **kwargs)
        MFSimulation.load_exchanges(nam, exchanges, **kwargs)
        MFSimulation.load_solvers(nam, solvers, **kwargs)

        return cls(
            name=sim_name,
            tdis=tdis,
            models=models,
            exchanges=exchanges,
            solvers=solvers,
            nam=nam,
        )

    @staticmethod
    def load_tdis(
        blocks: Dict[str, MFBlock],
        mempath,
        **kwargs,
    ):
        """Load simulation timing"""
        tdis = None
        assert "timing" in blocks
        for param_name, param in blocks["timing"].items():
            if param_name != "tdis6":
                continue
            tdis_fpth = param.value
            if tdis_fpth is None:
                raise ValueError("Invalid mfsim.name TDIS6 specification")
            with open(tdis_fpth, "r") as f:
                kwargs["mempath"] = f"{mempath}"
                tdis = SimTdis.load(f, **kwargs)
        return tdis

    @staticmethod
    def load_models(
        blocks: Dict[str, MFBlock],
        models: Dict[str, MFModel],
        mempath,
        **kwargs,
    ):
        """Load simulation models"""
        assert "models" in blocks
        for param_name, param in blocks["models"].items():
            if param_name != "models":
                continue
            assert "mtype" in param.value
            assert "mfname" in param.value
            assert "mname" in param.value
            for i in range(len(param.value["mtype"])):
                mtype = param.value["mtype"][i]
                mfname = param.value["mfname"][i]
                mname = param.value["mname"][i]
                if mtype.lower() == "gwe6":
                    model = GweModel
                elif mtype.lower() == "gwf6":
                    model = GwfModel
                elif mtype.lower() == "gwt6":
                    model = GwtModel
                elif mtype.lower() == "prt6":
                    model = PrtModel
                else:
                    model = None
                with open(mfname, "r") as f:
                    kwargs["mtype"] = mtype.lower()
                    kwargs["mempath"] = f"{mempath}/{mname}"
                    models[mname] = model.load(f, **kwargs)

    @staticmethod
    def load_exchanges(
        blocks: Dict[str, MFBlock],
        exchanges: Dict[str, Dict],
        mempath,
        **kwargs,
    ):
        """Load simulation exchanges"""
        assert "exchanges" in blocks
        for param_name, param in blocks["exchanges"].items():
            if param_name != "exchanges":
                continue
            if (
                "exgtype" not in param.value
                or "exgfile" not in param.value
                or "exgmnamea" not in param.value
                or "exgmnameb" not in param.value
            ):
                break
            for i in range(len(param.value["exgtype"])):
                exgtype = param.value["exgtype"][i]
                exgfile = param.value["exgfile"][i]
                # exgmnamea = param.value["exgmnamea"][i]
                # exgmnameb = param.value["exgmnameb"][i]
                if exgtype.lower() == "gwf6-gwf6":
                    exch = ExgGwfgwf
                else:
                    exch = None
                with open(exgfile, "r") as f:
                    ename = exgtype.replace("6", "")
                    ename = f"{ename}_{i}"
                    kwargs["mempath"] = f"{mempath}/{ename}"
                    exchanges[ename] = exch.load(f, **kwargs)

    @staticmethod
    def load_solvers(
        blocks: Dict[str, MFBlock],
        solvers: Dict[str, Dict],
        mempath,
        **kwargs,
    ):
        """Load simulation solvers"""
        assert "solutiongroup" in blocks
        for param_name, param in blocks["solutiongroup"].items():
            if param_name != "solutiongroup":
                continue
            if (
                "slntype" not in param.value
                or "slnfname" not in param.value
                or "slnmnames" not in param.value
            ):
                break
            for i in range(len(param.value["slntype"])):
                slntype = param.value["slntype"][i]
                slnfname = param.value["slnfname"][i]
                # slnmnames = param.value["slnmnames"][i]
                if slntype.lower() == "ims6":
                    sln = SlnIms
                else:
                    sln = None
                with open(slnfname, "r") as f:
                    slnname = slntype.replace("6", "")
                    slnname = f"{slnname}_{i}"
                    kwargs["mempath"] = f"{mempath}/{slnname}"
                    solvers[slnname] = sln.load(f, **kwargs)

    def write(self, basepath, **kwargs):
        """Write the simulation to files."""
        path = Path(basepath)
        with open(path / "mfsim.nam", "w") as f:
            self.nam.write(f, **kwargs)
        with open(path / f"{self.name}.tdis", "w") as f:
            self.tdis.write(f, **kwargs)
        for model in self.models:
            self.models[model].write(basepath, **kwargs)
