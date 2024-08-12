from typing import Dict, Optional

from flopy4.ispec.gwf_model import GwfModel
from flopy4.resolver import Resolve
from flopy4.utils import strip


class MFSimulation:
    """
    MF6 simulation.

    Notes
    -----
    TODO:
    This is a skelton class intended to support
    creating an MVP GWF model.  Reimplement and
    extend.
    """

    def __init__(
        self,
        name: Optional[str] = "sim",
        models: Optional[Dict[str, Dict]] = {},
    ):
        self.name = name
        self.mempath = name
        self.models = models

        self._resolv = Resolve(name=name, models=models)

    @classmethod
    def load(cls, f, **kwargs):
        """Load mfsim.nam from file."""
        models = dict()
        sim_name = "sim"

        while True:
            # pos = f.tell()
            line = f.readline()
            if line == "":
                break
            if line == "\n":
                continue
            line = strip(line).lower()
            words = line.split()
            # TODO: Temporary code. Reimplement below to load
            #       dfn block specification with MFList support
            if words[0] == "begin" and words[1] == "models":
                count = 0
                while True:
                    count += 1
                    line = f.readline()
                    line = strip(line).lower()
                    if line == "":
                        break
                    if line == "\n":
                        continue
                    words = line.split()
                    if words[0] == "end" and words[1] == "models":
                        break
                    elif len(words) > 1:
                        mtype = words[0]
                        fpth = words[1]
                        if len(words) > 2:
                            mname = words[2]
                        else:
                            mname = f"{mtype}-{count}"
                    kwargs["mempath"] = f"{sim_name}/{mname}"
                    with open(fpth, "r") as f_model:
                        models[mname] = GwfModel.load(f_model, **kwargs)

        return cls(name=sim_name, models=models)
