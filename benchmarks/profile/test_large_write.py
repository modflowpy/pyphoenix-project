# flopy4's constructor annotations are narrower than its converters accept
# mypy: disable-error-code="arg-type,list-item,misc"
"""Writes of large models built from scratch: flopy4's input forms
(lists, grids, arrays, NetCDF), and flopy3.

Each source model comes from the registry (downloaded on first use) and
is loaded with flopy3 once, for its data. Each variant builds a model from
that data, untimed, then writes it, into the same directory each round.

test1000_751x751 (1 layer x 751 x 751 = 564K cells, 3 stress periods):

- `test_test1000_sparse` -- WEL (1 cell) + CHD (1,550 cells): as lists,
  as grids (WELG + CHDG) in text or NetCDF, and flopy3's lists.
- `test_test1000_rch` -- recharge on every cell, `uniform` or `hetero`
  (from K): as a list (RCH, 1.7M entries; slow), as an array (RCHA) in
  text or NetCDF, and flopy3's list (slow) and array.

test1005_secp (16 x 130 x 275 = 572K cells, 6 stress periods):

- `test_test1005` -- WEL (3,971 cells x 6 periods) + CHD (18,647 cells) +
  RCHA: as lists, as grids in NetCDF (as text, the grids' 34M elements are
  too slow to bother with), and flopy3's lists.
"""

from types import SimpleNamespace

import numpy as np
import pytest
from _scenario import bench, netcdf_write, spd

NETCDF = {
    "netcdf-mesh": dict(layered_mesh=True, mesh2d=True),
    "netcdf-structured": dict(layered_mesh=False, mesh2d=False),
}


def _source(tmp_path_factory, name: str):
    """The registry model `name`'s flow model, loaded with flopy3."""
    import flopy
    from modflow_devtools.models import copy_to

    ws = copy_to(tmp_path_factory.mktemp("source"), name, verbose=False)
    if ws is None:
        pytest.fail(f"{name} not found in the registry")
    return flopy.mf6.MFSimulation.load(sim_ws=str(ws), verbosity_level=0).get_model()


def _grid_array(nper: int, shape: tuple, data: dict[int, dict]) -> np.ndarray:
    """Per-period cell values as a grid, `FILL_DNODATA` elsewhere."""
    from flopy4.mf6.constants import FILL_DNODATA

    arr = np.full((nper, *shape), FILL_DNODATA)
    for period, cells in data.items():
        for cellid, value in cells.items():
            arr[(period, *cellid)] = value
    return arr


class Model:
    """A model to build in either library, from a source model's data."""

    name: str
    perioddata: list[tuple[float, int, float]]

    def __init__(self, k: np.ndarray):
        self.k = k
        self.shape = k.shape
        self.nlay, self.nrow, self.ncol = k.shape
        self.ncpl = self.nrow * self.ncol
        self.nper = len(self.perioddata)

    def grid(self):
        raise NotImplementedError

    def ims(self):
        raise NotImplementedError

    def base4(self, dims) -> dict:
        raise NotImplementedError

    def flopy4(self, ws, packages) -> SimpleNamespace:
        """The model in flopy4, in `ws`, with the packages `packages(dims)`
        returns. Returns the simulation, model, grid and time discretization."""
        import flopy4

        grid = self.grid()
        dims = {"nper": self.nper, **grid.dims}
        time = flopy4.mf6.utils.time.Time(
            perlen=[p[0] for p in self.perioddata],
            nstp=[p[1] for p in self.perioddata],
            tsmult=[p[2] for p in self.perioddata],
        )
        gwf = flopy4.mf6.gwf.Gwf(
            name=self.name, dis=grid, **self.base4(dims), **packages(dims), dims=dims
        )
        sim = flopy4.mf6.simulation.Simulation(
            name=self.name,
            tdis=flopy4.mf6.simulation.Tdis.from_time(time),
            models=[gwf],
            solutiongroup=[self.ims()],
            workspace=ws,
        )
        return SimpleNamespace(sim=sim, gwf=gwf, grid=grid, time=time)


class Model1000(Model):
    name = "test1000"
    perioddata = [(1.0, 1, 1.0), (1000.0, 10, 1.5), (1.0, 1, 1.0)]

    def __init__(self, gwf3):
        super().__init__(gwf3.npf.k.array)
        self.chd = {
            tuple(int(x) for x in rec[0]): float(rec[1])
            for rec in gwf3.chd.stress_period_data.data[0]
        }
        self.wel = {
            tuple(int(x) for x in rec[0]): float(rec[1])
            for rec in gwf3.wel.stress_period_data.data[1]
        }
        self.rch = {
            "uniform": np.full((self.nper, self.ncpl), 0.001),
            "hetero": np.stack([(self.k[0] * 1e-5).reshape(self.ncpl)] * self.nper),
        }

    def rch_list(self, data: str) -> dict[int, dict]:
        """Recharge per period, per cell (the RCH list)."""
        arr, ncol = self.rch[data], self.ncol
        return {
            p: {(0, i // ncol, i % ncol): float(arr[p, i]) for i in range(self.ncpl)}
            for p in range(self.nper)
        }

    def grid(self):
        import flopy4

        nlay, nrow, ncol = self.shape
        return flopy4.mf6.utils.grid.StructuredGrid(
            nlay=nlay,
            nrow=nrow,
            ncol=ncol,
            top=np.full((nrow, ncol), 100.0),
            botm=np.full((1, nrow, ncol), -100.0),
            delr=np.full(ncol, 25.6),
            delc=np.full(nrow, 25.6),
            idomain=np.ones(self.shape, dtype=int),
        )

    def ims(self):
        import flopy4

        return flopy4.mf6.Ims(
            print_option="summary",
            outer_dvclose=1e-6,
            outer_maximum=100,
            inner_dvclose=1e-6,
            rclose=flopy4.mf6.Ims.Rclose(inner_rclose=0.01),
            inner_maximum=100,
            linear_acceleration="cg",
            scaling_method=None,
            reordering_method=None,
            relaxation_factor=1.0,
            models=[self.name],
        )

    def base4(self, dims) -> dict:
        from pathlib import Path

        from flopy4.mf6 import gwf

        return dict(
            ic=gwf.Ic(strt=0.0, dims=dims),
            npf=gwf.Npf(
                icelltype=np.ones(self.shape, dtype=int), k=self.k, save_flows=True, dims=dims
            ),
            sto=gwf.Sto(ss=0.0, sy=0.1, iconvert=1, dims=dims),
            oc=gwf.Oc(
                budget_file=Path(f"{self.name}.cbc"),
                head_file=Path(f"{self.name}.hds"),
                stress_period_data={0: [("SAVE", "HEAD", "LAST"), ("SAVE", "BUDGET", "LAST")]},
                dims=dims,
            ),
        )

    def flopy3(self, ws):
        """The base model in flopy3, in `ws`: (simulation, flow model)."""
        import flopy

        sim = flopy.mf6.MFSimulation(sim_name=self.name, sim_ws=str(ws), verbosity_level=0)
        flopy.mf6.ModflowTdis(sim, nper=self.nper, perioddata=self.perioddata)
        flopy.mf6.ModflowIms(
            sim,
            outer_dvclose=1e-6,
            outer_maximum=100,
            inner_dvclose=1e-6,
            rcloserecord=0.01,
            inner_maximum=100,
            linear_acceleration="cg",
            scaling_method="none",
            reordering_method="none",
            relaxation_factor=1.0,
        )
        gwf = flopy.mf6.ModflowGwf(sim, modelname=self.name)
        flopy.mf6.ModflowGwfdis(
            gwf,
            nlay=self.nlay,
            nrow=self.nrow,
            ncol=self.ncol,
            delr=25.6,
            delc=25.6,
            top=100.0,
            botm=-100.0,
            idomain=np.ones(self.shape, dtype=int),
        )
        flopy.mf6.ModflowGwfic(gwf, strt=0.0)
        flopy.mf6.ModflowGwfnpf(gwf, icelltype=1, k=self.k, save_flows=True)
        flopy.mf6.ModflowGwfsto(
            gwf,
            ss=0.0,
            sy=0.1,
            iconvert=1,
            save_flows=True,
            steady_state={0: True, 2: True},
            transient={1: True},
        )
        flopy.mf6.ModflowGwfoc(
            gwf,
            budget_filerecord=f"{self.name}.cbc",
            head_filerecord=f"{self.name}.hds",
            saverecord={0: [("HEAD", "LAST"), ("BUDGET", "LAST")]},
        )
        return sim, gwf


class Model1005(Model):
    name = "test1005"
    perioddata = [
        (1.0, 2, 1.1),
        (3651.0, 2, 1.1),
        (3652.0, 2, 1.1),
        (3653.0, 2, 1.1),
        (3652.0, 2, 1.1),
        (3653.0, 2, 1.1),
    ]

    def __init__(self, gwf3):
        super().__init__(gwf3.npf.k.array)
        self.ss = gwf3.sto.ss.array
        self.botm = gwf3.dis.botm.array
        self.rcha = gwf3.rch.recharge.array[:, 0].reshape(self.nper, self.ncpl)
        # drop WEL's auxiliary iface column
        self.wel = {
            period: {tuple(int(x) for x in rec[0]): float(rec[1]) for rec in records}
            for period, records in gwf3.wel.stress_period_data.data.items()
        }
        # constant head 0, with the time series stripped
        self.chd = {
            tuple(int(x) for x in rec[0]): 0.0 for rec in gwf3.chd.stress_period_data.data[0]
        }

    def grid(self):
        import flopy4

        nlay, nrow, ncol = self.shape
        return flopy4.mf6.utils.grid.StructuredGrid(
            nlay=nlay,
            nrow=nrow,
            ncol=ncol,
            top=np.zeros((nrow, ncol)),
            botm=self.botm,
            delr=np.full(ncol, 10560.0),
            delc=np.full(nrow, 10560.0),
            idomain=np.ones(self.shape, dtype=int),
        )

    def ims(self):
        import flopy4

        return flopy4.mf6.Ims(
            outer_dvclose=1e-6,
            outer_maximum=200,
            inner_dvclose=1e-7,
            rclose=flopy4.mf6.Ims.Rclose(inner_rclose=0.01),
            inner_maximum=100,
            linear_acceleration="bicgstab",
            models=[self.name],
        )

    def base4(self, dims) -> dict:
        from pathlib import Path

        from flopy4.mf6 import gwf

        return dict(
            ic=gwf.Ic(strt=0.0, dims=dims),
            npf=gwf.Npf(
                icelltype=np.zeros(self.shape, dtype=int), k=self.k, save_flows=True, dims=dims
            ),
            sto=gwf.Sto(ss=self.ss, sy=0.0, iconvert=0, dims=dims),
            oc=gwf.Oc(
                budget_file=Path(f"{self.name}.cbc"),
                head_file=Path(f"{self.name}.hds"),
                stress_period_data={0: [("SAVE", "HEAD", "LAST"), ("SAVE", "BUDGET", "LAST")]},
                dims=dims,
            ),
            rch=[gwf.Rcha(recharge=self.rcha, dims=dims)],
        )

    def flopy3(self, ws):
        """The model in flopy3, in `ws`, with its WEL and CHD lists."""
        import flopy

        sim = flopy.mf6.MFSimulation(sim_name=self.name, sim_ws=str(ws), verbosity_level=0)
        flopy.mf6.ModflowTdis(sim, nper=self.nper, perioddata=self.perioddata)
        flopy.mf6.ModflowIms(
            sim,
            outer_dvclose=1e-6,
            outer_maximum=200,
            inner_dvclose=1e-7,
            rcloserecord=0.01,
            inner_maximum=100,
            linear_acceleration="bicgstab",
        )
        gwf = flopy.mf6.ModflowGwf(sim, modelname=self.name)
        flopy.mf6.ModflowGwfdis(
            gwf,
            nlay=self.nlay,
            nrow=self.nrow,
            ncol=self.ncol,
            delr=10560.0,
            delc=10560.0,
            top=np.zeros((self.nrow, self.ncol)),
            botm=self.botm,
            idomain=np.ones(self.shape, dtype=int),
        )
        flopy.mf6.ModflowGwfic(gwf, strt=0.0)
        flopy.mf6.ModflowGwfnpf(gwf, icelltype=0, k=self.k, save_flows=True)
        flopy.mf6.ModflowGwfsto(
            gwf, ss=self.ss, sy=0.0, iconvert=0, save_flows=True, steady_state={0: True}
        )
        flopy.mf6.ModflowGwfrcha(
            gwf, recharge={p: self.rcha[p].reshape(self.nrow, self.ncol) for p in range(self.nper)}
        )
        flopy.mf6.ModflowGwfchd(
            gwf, print_flows=True, save_flows=True, stress_period_data={0: list(self.chd.items())}
        )
        flopy.mf6.ModflowGwfwel(
            gwf,
            save_flows=True,
            stress_period_data={p: list(cells.items()) for p, cells in self.wel.items()},
        )
        flopy.mf6.ModflowGwfoc(
            gwf,
            budget_filerecord=f"{self.name}.cbc",
            head_filerecord=f"{self.name}.hds",
            saverecord={0: [("HEAD", "LAST"), ("BUDGET", "LAST")]},
        )
        return sim


@pytest.fixture(scope="module")
def test1000(tmp_path_factory) -> Model1000:
    return Model1000(_source(tmp_path_factory, "mf6/large/test1000_751x751"))


@pytest.fixture(scope="module")
def test1005(tmp_path_factory) -> Model1005:
    return Model1005(_source(tmp_path_factory, "mf6/large/test1005_secp"))


def _write4(benchmark, m: SimpleNamespace, variant: str, slow: bool = False) -> None:
    if variant in NETCDF:
        bench(benchmark, netcdf_write(m.sim, m.gwf, m.grid, m.time, **NETCDF[variant]), slow)
    else:
        bench(benchmark, m.sim.write, slow)


def _write3(benchmark, sim3, slow: bool = False) -> None:
    bench(benchmark, lambda: sim3.write_simulation(silent=True), slow)


@pytest.mark.parametrize("variant", ["list", "grid", *NETCDF, "flopy3"])
def test_test1000_sparse(benchmark, quiet, tmp_path, test1000, variant):
    from flopy4.mf6 import gwf

    t = test1000
    benchmark.group = "test1000-sparse"
    if variant == "flopy3":
        import flopy

        sim3, gwf3 = t.flopy3(tmp_path)
        flopy.mf6.ModflowGwfchd(
            gwf3, print_flows=True, save_flows=True, stress_period_data={0: list(t.chd.items())}
        )
        flopy.mf6.ModflowGwfwel(gwf3, save_flows=True, stress_period_data={1: list(t.wel.items())})
        _write3(benchmark, sim3)
        return

    def lists(dims):
        return dict(
            chd=gwf.Chd(
                stress_period_data=spd({0: t.chd}), print_flows=True, save_flows=True, dims=dims
            ),
            wel=gwf.Wel(stress_period_data=spd({1: t.wel}), save_flows=True, dims=dims),
        )

    def grids(dims):
        chd = _grid_array(t.nper, t.shape, {0: t.chd})
        wel = _grid_array(t.nper, t.shape, {1: t.wel})
        return dict(
            chd=gwf.Chdg(head=chd, print_flows=True, save_flows=True, dims=dims),
            wel=gwf.Welg(q=wel, save_flows=True, dims=dims),
        )

    _write4(benchmark, t.flopy4(tmp_path, lists if variant == "list" else grids), variant)


@pytest.mark.parametrize("data", ["uniform", "hetero"])
@pytest.mark.parametrize(
    "variant",
    [
        pytest.param("list", marks=pytest.mark.slow),
        "array",
        *NETCDF,
        pytest.param("flopy3-list", marks=pytest.mark.slow),
        "flopy3-array",
    ],
)
def test_test1000_rch(benchmark, quiet, tmp_path, test1000, data, variant):
    from flopy4.mf6 import gwf

    t = test1000
    benchmark.group = f"test1000-rch[{data}]"
    slow = variant in ("list", "flopy3-list")
    if variant.startswith("flopy3"):
        import flopy

        sim3, gwf3 = t.flopy3(tmp_path)
        if variant == "flopy3-list":
            spd3 = spd(t.rch_list(data))
            flopy.mf6.ModflowGwfrch(gwf3, stress_period_data=spd3)
        elif data == "uniform":
            flopy.mf6.ModflowGwfrcha(gwf3, recharge=float(t.rch["uniform"][0, 0]))
        else:
            arr = t.rch[data]
            recharge = {p: arr[p].reshape(t.nrow, t.ncol) for p in range(t.nper)}
            flopy.mf6.ModflowGwfrcha(gwf3, recharge=recharge)
        _write3(benchmark, sim3, slow)
        return

    if variant == "list":
        rch_list = spd(t.rch_list(data))

        def packages(dims):
            return dict(rch=[gwf.Rch(stress_period_data=rch_list, dims=dims)])
    else:

        def packages(dims):
            return dict(rch=[gwf.Rcha(recharge=t.rch[data], dims=dims)])

    _write4(benchmark, t.flopy4(tmp_path, packages), variant, slow)


@pytest.mark.parametrize("variant", ["list", *NETCDF, "flopy3"])
def test_test1005(benchmark, quiet, tmp_path, test1005, variant):
    from flopy4.mf6 import gwf

    t = test1005
    benchmark.group = "test1005"
    if variant == "flopy3":
        _write3(benchmark, t.flopy3(tmp_path))
        return

    def lists(dims):
        return dict(
            chd=gwf.Chd(
                stress_period_data=spd({0: t.chd}), print_flows=True, save_flows=True, dims=dims
            ),
            wel=gwf.Wel(stress_period_data=spd(t.wel), save_flows=True, dims=dims),
        )

    def grids(dims):
        chd = _grid_array(t.nper, t.shape, {0: t.chd})
        wel = _grid_array(t.nper, t.shape, t.wel)
        return dict(
            chd=gwf.Chdg(head=chd, print_flows=True, save_flows=True, dims=dims),
            wel=gwf.Welg(q=wel, save_flows=True, dims=dims),
        )

    _write4(benchmark, t.flopy4(tmp_path, lists if variant == "list" else grids), variant)
