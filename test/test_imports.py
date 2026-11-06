import subprocess
import sys
import textwrap

# Imported by the grid, time and output-reading code, and loaded only when
# it's used: flopy, xugrid, and what they import.
LAZY = ["flopy", "xugrid", "numba", "dask", "matplotlib", "shapely", "pyproj"]

_SCRIPT = """
import sys
from pathlib import Path

from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.tdis import Tdis

ws = Path(sys.argv[1])
sim = Simulation(
    tdis=Tdis(nper=1, perioddata=[(1.0, 1, 1.0)]),
    workspace=ws,
    name="sim",
    solutiongroup=[Ims(models=["gwf"])],
)
gwf = Gwf(parent=sim, dis=Dis(nlay=1, nrow=3, ncol=3, top=1.0, botm=0.0), name="gwf")
Ic(parent=gwf)
Npf(parent=gwf, k=1.0)
Oc(parent=gwf, head_file="gwf.hds", stress_period_data={0: [("SAVE", "HEAD", "ALL")]})
Chd(parent=gwf, stress_period_data={0: [[(0, 0, 0), 1.0]]})
sim.write()
Simulation.load(ws / "mfsim.nam")
print(" ".join(sorted({m.split(".")[0] for m in sys.modules})))
"""


def test_load_and_write_skip_interop_imports(tmp_path):
    """Building, writing and loading a simulation doesn't import flopy or
    xugrid (see `flopy4.mf6.utils`)."""
    out = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(_SCRIPT), str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    imported = set(out.stdout.split())
    assert not imported & set(LAZY), sorted(imported & set(LAZY))
