"""Compare flopy4's NetCDF period arrays with the arrays MF6 exports
(EXPORT_ARRAY_NETCDF) for the same model.

Needs an MF6 on PATH with NetCDF support that exports the values held in
each period (MF6 6.9 or later); skipped otherwise.
"""

import re
import shutil
import subprocess

import numpy as np
import pytest
import xarray as xr

from flopy4.mf6 import Ims
from flopy4.mf6.constants import FILL_DNODATA as NO
from flopy4.mf6.gwf import Chdg, Dis, Disv, Evta, Gwf, Ic, Npf, Oc, Rcha, Rivg, Welg
from flopy4.mf6.netcdf import NetCDFFormat, NetCDFModel
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.time import Time

NLAY, NROW, NCOL, NPER = 2, 2, 3, 4
NODES = NLAY * NROW * NCOL
# coordinate variables, compared separately from the period arrays: MF6
# writes units "m" when LENUNI is undefined, flopy4 leaves units out
COORDS = ("x", "y", "mesh_face_x", "mesh_face_y")


def _mf6_version(exe: str) -> tuple[int, int] | None:
    out = subprocess.run([exe, "-v"], capture_output=True, text=True).stdout
    m = re.search(r"(\d+)\.(\d+)\.\d+", out)
    return (int(m[1]), int(m[2])) if m else None


@pytest.fixture
def mf6_exe():
    exe = shutil.which("mf6")
    if exe is None:
        pytest.skip("mf6 not on PATH")
    version = _mf6_version(exe)
    if version is None or version < (6, 9):
        pytest.skip(f"mf6 {version} doesn't export period values (needs 6.9 or later)")
    return exe


def _grid(cells: dict) -> np.ndarray:
    a = np.full(NODES, NO)
    for n, v in cells.items():
        a[n] = v
    return a


def _disv(idomain: np.ndarray) -> Disv:
    """The DIS grid as DISV: cells by row, then column."""
    ncpl = NROW * NCOL
    nvert = (NROW + 1) * (NCOL + 1)
    cell2d = []
    for n in range(ncpl):
        i, j = divmod(n, NCOL)
        v = i * (NCOL + 1) + j
        # clockwise from the upper left
        verts = (v, v + 1, v + NCOL + 2, v + NCOL + 1)
        cell2d.append(Disv.Cell2d(n, j + 0.5, NROW - i - 0.5, 4, verts))
    return Disv(
        nlay=NLAY,
        ncpl=ncpl,
        nvert=nvert,
        top=np.full(ncpl, 10.0),
        botm=np.stack([np.full(ncpl, 5.0), np.full(ncpl, 0.0)]),
        idomain=idomain.reshape(NLAY, ncpl),
        vertices=dict(
            iv=np.arange(nvert),
            xv=np.tile(np.arange(NCOL + 1, dtype=float), NROW + 1),
            yv=np.repeat(np.arange(NROW, -1, -1, dtype=float), NCOL + 1),
        ),
        cell2d=cell2d,
        export_array_netcdf=True,
    )


def _simulation(workspace, disv: bool, mesh: bool):
    name = "parity"
    sim = Simulation(
        tdis=Time(perlen=[1.0] * NPER, nstp=[1] * NPER, tsmult=[1.0] * NPER),
        workspace=workspace,
        name="sim",
        solutiongroup=[Ims(models=[name], linear_acceleration="bicgstab")],
    )
    # a date only: MF6 writes it as given in the time units
    sim.tdis.start_date_time = "2020-01-01"
    idomain = np.ones((NLAY, NROW, NCOL), dtype=int)
    idomain[1, 1, 2] = 0
    dis = (
        _disv(idomain)
        if disv
        else Dis(
            nlay=NLAY,
            nrow=NROW,
            ncol=NCOL,
            top=10.0,
            botm=np.array([5.0, 0.0]),
            idomain=idomain,
            export_array_netcdf=True,
        )
    )
    gwf = Gwf(parent=sim, dis=dis, name=name)
    ncfile = f"{name}.nc"
    if mesh:
        gwf.netcdf_mesh2d_file = ncfile
    else:
        gwf.netcdf_structured_file = ncfile
    Ic(parent=gwf, strt=8.0)
    Npf(parent=gwf, icelltype=0, k=1.0)
    Oc(parent=gwf, head_file=f"{name}.hds", stress_period_data={0: [("SAVE", "HEAD", "LAST")]})
    # head carried forward, changed in period 3
    Chdg(
        parent=gwf,
        head={0: _grid({0: 8.0, 11: 7.0}), 2: _grid({0: 9.0, 6: 7.5})},
        export_array_netcdf=True,
    )
    # wells: aux per name, an aux value off the boundary, an inactive cell,
    # an aux-only block (q held), a cleared period and new boundary cells
    wells = {1: -0.1, 4: -0.2, 7: 3.0, 11: -0.3}
    Welg(
        parent=gwf,
        auxiliary=["m1", "m2"],
        q={0: _grid(wells), 2: None, 3: _grid({2: -0.4})},
        aux={
            0: {
                "m1": _grid({1: 1.0, 4: 2.0, 5: 9.0, 7: 1.5, 11: 2.5}),
                "m2": _grid({1: 3.0, 4: 4.0, 7: 3.5, 11: 4.5}),
            },
            1: {"m1": _grid(dict.fromkeys(wells, 6.0)), "m2": _grid(dict.fromkeys(wells, 7.0))},
            3: {"m1": _grid({2: 5.0}), "m2": _grid({2: 6.0})},
        },
        export_array_netcdf=True,
    )
    # a second WELG: switched off for a period, then on again with its aux
    # values held
    Welg(
        parent=gwf,
        auxiliary=["m1"],
        q={0: _grid({3: -0.5, 8: -0.6}), 1: None, 2: _grid({3: -0.7, 8: -0.8})},
        aux={0: {"m1": _grid({3: 1.2, 8: 1.3})}},
        export_array_netcdf=True,
    )
    # a block giving only one array, the others held
    rivers = {5: 6.0, 9: 5.5}
    Rivg(
        parent=gwf,
        stage={0: _grid(rivers), 1: _grid(dict.fromkeys(rivers, 6.5))},
        cond={0: _grid(dict.fromkeys(rivers, 10.0))},
        rbot={0: _grid(dict.fromkeys(rivers, 4.0))},
        export_array_netcdf=True,
    )
    # layer arrays: recharge held through a block that gives only an aux
    # array, the layer index held until given
    ncpl = NROW * NCOL
    Rcha(
        parent=gwf,
        auxiliary=["c"],
        recharge={0: np.full(ncpl, 1.0e-3), 2: np.full(ncpl, 2.0e-3)},
        irch={3: np.ones(ncpl, dtype=int)},
        aux={0: {"c": np.full(ncpl, 0.5)}, 1: {"c": np.full(ncpl, 0.7)}},
        export_array_netcdf=True,
    )
    # one array changed, the others and the layer index held
    Evta(
        parent=gwf,
        surface={0: np.full(ncpl, 9.0)},
        rate={0: np.full(ncpl, 1.0e-4), 2: np.full(ncpl, 3.0e-4)},
        depth={0: np.full(ncpl, 2.0)},
        ievt={1: np.zeros(ncpl, dtype=int)},
        export_array_netcdf=True,
    )
    return sim, gwf, ncfile


def _norm(a) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    assert not np.isnan(a).any()
    return np.where(np.abs(a) >= 1.0e30, NO, a)


def _assert_attrs_equal(attrs4: dict, attrs6: dict, name: str) -> None:
    assert set(attrs4) == set(attrs6), name
    for a, v in attrs6.items():
        assert np.array_equal(np.asarray(attrs4[a]), np.asarray(v)), f"{name}.{a}"


@pytest.mark.parametrize(
    "disv, mesh",
    [(False, False), (False, True), (True, True)],
    ids=["dis-structured", "dis-mesh", "disv-mesh"],
)
def test_period_arrays_match_mf6_export(function_tmpdir, mf6_exe, disv, mesh):
    sim, gwf, ncfile = _simulation(function_tmpdir, disv, mesh)
    sim.write()
    # MF6 exports input arrays in validate mode
    run = subprocess.run(
        [mf6_exe, "--mode=validate"], cwd=function_tmpdir, capture_output=True, text=True
    )
    out = run.stdout + run.stderr
    if "NetCDF libraries are not available" in out:
        pytest.skip("mf6 built without NetCDF")
    assert run.returncode == 0, out

    fmt = NetCDFFormat.LAYERED_MESH if mesh else NetCDFFormat.STRUCTURED
    fp4file = function_tmpdir / "flopy4.nc"
    NetCDFModel.from_model(
        gwf, netcdf_format=fmt, grid=gwf.dis.to_grid(), time=sim.tdis.to_time()
    ).to_netcdf(fp4file)
    opts = dict(decode_times=False, mask_and_scale=False, decode_coords=False)
    with (
        xr.open_dataset(fp4file, **opts) as ds4,
        xr.open_dataset(function_tmpdir / ncfile, **opts) as ds6,
    ):
        v6 = {k for k, v in ds6.data_vars.items() if "time" in v.dims}
        v4 = {k for k, v in ds4.data_vars.items() if "time" in v.dims}
        assert v6, "mf6 exported no period arrays"
        assert v6 == v4
        for k in sorted(v6):
            assert ds4[k].dtype == ds6[k].dtype, k
            np.testing.assert_allclose(_norm(ds4[k].values), _norm(ds6[k].values), err_msg=k)
            _assert_attrs_equal(ds4[k].attrs, ds6[k].attrs, k)
        for c in ("time", "time_bnds"):
            np.testing.assert_allclose(ds4[c].values, ds6[c].values, err_msg=c)
            _assert_attrs_equal(ds4[c].attrs, ds6[c].attrs, c)
        for c in COORDS:
            if c in ds6.variables:
                attrs6 = {a: v for a, v in ds6[c].attrs.items() if a != "units"}
                assert dict(ds4[c].attrs) == attrs6, c
        if "layer" in ds6.variables:
            assert ds4["layer"].dtype == ds6["layer"].dtype
            np.testing.assert_array_equal(ds4["layer"].values, ds6["layer"].values)
            _assert_attrs_equal(ds4["layer"].attrs, ds6["layer"].attrs, "layer")
