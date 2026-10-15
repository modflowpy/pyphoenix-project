"""Two GWF models coupled by a GWF6-GWF6 exchange, run with flopy4's own
`Simulation.run(ncpus=...)`. The parallel run needs an extended (MPI-capable)
mf6 build, so it's gated behind `MF6_EXTENDED`, matching the rest of the repo.
"""

import os

import numpy as np

from flopy4.mf6.exg import Gwfgwf
from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.time import Time

NCOL = 5
DELR = DELC = 100.0
NAME_LEFT = "left"
NAME_RIGHT = "right"


def _build(workspace):
    ims = Ims(
        filename="sln1.ims",
        models=[NAME_LEFT, NAME_RIGHT],
        outer_dvclose=1.0e-8,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1.0e-8,
        rclose=Ims.Rclose(inner_rclose=1.0e-3),
        linear_acceleration="bicgstab",
        relaxation_factor=0.97,
    )
    sim = Simulation(
        name="par",
        workspace=workspace,
        tdis=Time(perlen=[1.0], nstp=[1], tsmult=[1.0]),
        solutiongroup=[ims],
    )

    left = Gwf(
        parent=sim,
        name=NAME_LEFT,
        save_flows=True,
        dis=Dis(nlay=1, nrow=1, ncol=NCOL, delr=DELR, delc=DELC, top=0.0, botm=-100.0),
    )
    Ic(parent=left, strt=0.0)
    Npf(parent=left, k=1.0, icelltype=0)
    Chd(parent=left, stress_period_data={0: [[(0, 0, 0), 1.0]]})
    Oc(
        parent=left,
        head_file=f"{NAME_LEFT}.hds",
        stress_period_data={0: [("SAVE", "HEAD", "LAST")]},
    )

    right = Gwf(
        parent=sim,
        name=NAME_RIGHT,
        save_flows=True,
        dis=Dis(
            nlay=1,
            nrow=1,
            ncol=NCOL,
            delr=DELR,
            delc=DELC,
            top=0.0,
            botm=-100.0,
            xorigin=NCOL * DELR,
        ),
    )
    Ic(parent=right, strt=0.0)
    Npf(parent=right, k=1.0, icelltype=0)
    Chd(parent=right, stress_period_data={0: [[(0, 0, NCOL - 1), 10.0]]})
    Oc(
        parent=right,
        head_file=f"{NAME_RIGHT}.hds",
        stress_period_data={0: [("SAVE", "HEAD", "LAST")]},
    )

    Gwfgwf(
        parent=sim,
        name="leftright",
        exgmnamea=NAME_LEFT,
        exgmnameb=NAME_RIGHT,
        exchangedata=[((0, 0, NCOL - 1), (0, 0, 0), 1, DELR / 2, DELR / 2, DELC)],
    )

    return sim


def test_gwfgwf_parallel_run(function_tmpdir):
    """The coupled models solve a uniform 1D flow field (heads 1..10), the
    same whether run serially (ncpus=1) or under MPI (ncpus=2)."""
    from flopy.utils import HeadFile

    sim = _build(function_tmpdir)
    sim.write()

    if not os.getenv("MF6_EXTENDED"):
        return

    for ncpus in (1, 2):
        sim.run(ncpus=ncpus)
        with HeadFile(function_tmpdir / f"{NAME_LEFT}.hds", precision="double") as hf:
            heads_left = hf.get_data().flatten()
        with HeadFile(function_tmpdir / f"{NAME_RIGHT}.hds", precision="double") as hf:
            heads_right = hf.get_data().flatten()
        np.testing.assert_allclose(heads_left, [1.0, 2.0, 3.0, 4.0, 5.0])
        np.testing.assert_allclose(heads_right, [6.0, 7.0, 8.0, 9.0, 10.0])
