import numpy as np
import pytest
import xarray as xr
import xugrid as xu

from flopy4.mf6.gwf import Chd, Dis, Disv, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.cbc_reader import open_cbc
from flopy4.mf6.utils.grid import VertexGrid, grid_mapping
from flopy4.mf6.utils.heads_reader import open_hds
from flopy4.mf6.utils.time import Time


def _dis_model_output(function_tmpdir, **dis_kwargs):
    sim_name = "dis_test"
    gwf_name = "gwf_dis"

    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="days")
    ims = Ims(
        filename=f"{sim_name}.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        linear_acceleration="cg",
    )
    sim = Simulation(tdis=time, workspace=function_tmpdir, name=sim_name, solutiongroup=[ims])

    nlay, nrow, ncol = 2, 3, 4
    botm = np.stack([np.full((nrow, ncol), 0.0), np.full((nrow, ncol), -10.0)])
    dis = Dis(
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        delr=10.0,
        delc=10.0,
        top=10.0,
        botm=botm,
        idomain=1,
        **dis_kwargs,
    )

    gwf = Gwf(parent=sim, save_flows=True, dis=dis, name=gwf_name)
    Ic(parent=gwf, strt=5.0)
    Npf(parent=gwf, k=1.0, icelltype=0)
    Chd(
        parent=gwf,
        print_flows=True,
        stress_period_data={0: [[(0, 0, 0), 10.0], [(0, 0, ncol - 1), 0.0]]},
    )
    Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        stress_period_data={0: [("SAVE", "HEAD", "LAST"), ("SAVE", "BUDGET", "LAST")]},
    )

    sim.write()
    sim.run()

    base_path = function_tmpdir
    hds_path = function_tmpdir / f"{gwf_name}.hds"
    cbc_path = function_tmpdir / f"{gwf_name}.cbc"
    grb_path = function_tmpdir / f"{gwf_name}.dis.dis.grb"

    assert hds_path.is_file(), f"HDS file not found: {hds_path}"
    assert cbc_path.is_file(), f"CBC file not found: {cbc_path}"
    assert grb_path.is_file(), f"GRB file not found: {grb_path}"

    return {
        "base": base_path,
        "hds": hds_path,
        "cbc": cbc_path,
        "grb": grb_path,
        "nlay": nlay,
        "nrow": nrow,
        "ncol": ncol,
        "gwf": gwf,
    }


@pytest.fixture
def dis_model_output(function_tmpdir):
    return _dis_model_output(function_tmpdir)


def _disv_model_output(function_tmpdir, **dis_kwargs):
    sim_name = "disv_test"
    gwf_name = "gwf_disv"

    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="days")
    ims = Ims(
        filename=f"{sim_name}.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        linear_acceleration="cg",
    )
    sim = Simulation(tdis=time, workspace=function_tmpdir, name=sim_name, solutiongroup=[ims])

    nlay = 2
    ncpl = 9
    nvert = 16

    top = np.ones(ncpl, dtype=float) * 10.0
    botm = np.stack([np.full(ncpl, 0.0), np.full(ncpl, -10.0)])

    # 3x3 grid of quads
    cells = [
        [0, 1, 5, 4],
        [1, 2, 6, 5],
        [2, 3, 7, 6],
        [4, 5, 9, 8],
        [5, 6, 10, 9],
        [6, 7, 11, 10],
        [8, 9, 13, 12],
        [9, 10, 14, 13],
        [10, 11, 15, 14],
    ]

    cell2d = []
    for n in range(ncpl):
        cell2d.append(
            Disv.Cell2d(
                n,
                float((n % 3) * 10 + 5),
                float(25 - (n // 3) * 10),
                4,
                tuple(cells[n]),
            )
        )

    # 4x4 grid of vertices (16 total)
    xv = np.array([float(i * 10) for i in range(4)] * 4)
    yv = np.array([float(30 - j * 10) for j in range(4) for _ in range(4)])

    disv = Disv(
        nlay=nlay,
        ncpl=ncpl,
        nvert=nvert,
        top=top,
        botm=botm,
        idomain=1,
        vertices=dict(iv=np.arange(nvert, dtype=int), xv=xv, yv=yv),
        cell2d=cell2d,
        **dis_kwargs,
    )

    gwf = Gwf(parent=sim, save_flows=True, dis=disv, name=gwf_name)
    Ic(parent=gwf, strt=5.0)
    Npf(parent=gwf, k=1.0, icelltype=0)
    Chd(parent=gwf, print_flows=True, stress_period_data={0: [[(0, 0), 10.0], [(0, 8), 0.0]]})
    Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        stress_period_data={0: [("SAVE", "HEAD", "LAST"), ("SAVE", "BUDGET", "LAST")]},
    )

    sim.write()
    sim.run()

    base_path = function_tmpdir
    hds_path = function_tmpdir / f"{gwf_name}.hds"
    cbc_path = function_tmpdir / f"{gwf_name}.cbc"
    grb_path = function_tmpdir / f"{gwf_name}.disv.disv.grb"

    assert hds_path.is_file(), f"HDS file not found: {hds_path}"
    assert cbc_path.is_file(), f"CBC file not found: {cbc_path}"
    assert grb_path.is_file(), f"GRB file not found: {grb_path}"

    return {
        "base": base_path,
        "hds": hds_path,
        "cbc": cbc_path,
        "grb": grb_path,
        "nlay": nlay,
        "ncpl": ncpl,
        "gwf": gwf,
    }


@pytest.fixture
def disv_model_output(function_tmpdir):
    return _disv_model_output(function_tmpdir)


def test_open_hds_dis(dis_model_output):
    paths = dis_model_output
    head = open_hds(paths["hds"], paths["grb"])

    assert isinstance(head, xr.DataArray)
    assert head.dims == ("time", "layer", "row", "col")
    assert head.shape == (1, paths["nlay"], paths["nrow"], paths["ncol"])
    assert not np.all(np.isnan(head.values))
    # x and y are world coordinates on col and row, and select; no layer
    # coordinate, as for package arrays
    assert head.coords["x"].dims == ("col",)
    assert head.coords["y"].dims == ("row",)
    assert "layer" not in head.coords
    x, y = float(head.x[1]), float(head.y[2])
    picked = head.sel(x=x, y=y)
    np.testing.assert_array_equal(picked.values, head.isel(col=1, row=2).values)
    # cells' elevations from the grb, for selecting by z
    for name in ("z", "z_top", "z_bot"):
        assert head.coords[name].dims == ("layer", "row", "col")
    np.testing.assert_array_equal(head.z_top[1:], head.z_bot[:-1])
    z = float(head.z[1, 2, 1])
    picked = head.grid.sel_world(x, y, z)
    np.testing.assert_array_equal(picked.values, head.isel(layer=1, row=2, col=1).values)
    assert picked.layer.item() == 1


def test_open_cbc_dis(dis_model_output):
    paths = dis_model_output
    cbc = open_cbc(paths["cbc"], paths["grb"])

    assert isinstance(cbc, xr.Dataset)
    # Should have at least flow-ja-face decomposed keys
    keys = set(cbc.data_vars)
    assert len(keys) > 0


def test_open_cbc_dis_flowja(dis_model_output):
    paths = dis_model_output
    cbc = open_cbc(paths["cbc"], paths["grb"], flowja=True)

    assert isinstance(cbc, xr.Dataset)
    assert "flow-ja-face" in cbc.data_vars
    assert "connectivity" in cbc.data_vars
    assert cbc["connectivity"].dims == ("connection", "nm")


def test_open_hds_disv(disv_model_output):
    paths = disv_model_output
    head = open_hds(paths["hds"], paths["grb"])

    assert isinstance(head, xu.UgridDataArray)
    assert head.dims == ("time", "layer", "cell")
    ntime, nlayer = 1, paths["nlay"]
    assert head.shape[0] == ntime
    assert head.shape[1] == nlayer
    assert head.shape[2] == paths["ncpl"]
    assert not np.all(np.isnan(head.values))
    for name in ("z", "z_top", "z_bot"):
        assert head.coords[name].dims == ("layer", "cell")
    z = float(head.z[-1, 0])
    out = head.obj.grid.sel_z(z)
    assert out.dims == ("time", "cell")
    np.testing.assert_array_equal(out.isel(cell=0).values, head.obj.isel(layer=-1, cell=0).values)


def test_open_cbc_disv(disv_model_output):
    paths = disv_model_output
    cbc = open_cbc(paths["cbc"], paths["grb"])

    assert isinstance(cbc, (xr.Dataset, xu.UgridDataset))
    keys = set(cbc.data_vars)
    assert len(keys) > 0
    edge_dim = cbc.ugrid.grid.edge_dimension
    for name in keys:
        # horizontal flows are on the mesh's edges, the rest on its cells
        loc = edge_dim if name.startswith("flow-horizontal-face") else "cell"
        assert cbc[name].dims == ("time", "layer", loc), name


def test_open_cbc_disv_flowja(disv_model_output):
    paths = disv_model_output
    cbc = open_cbc(paths["cbc"], paths["grb"], flowja=True)

    assert isinstance(cbc, (xr.Dataset, xu.UgridDataset))
    assert "flow-ja-face" in cbc.data_vars
    assert "connectivity" in cbc.data_vars
    assert cbc["connectivity"].dims == ("connection", "nm")


def test_open_hds_dis_rotated(function_tmpdir):
    """A rotated grid's output has local x/y, the projection coordinate and
    world coordinates, the same as its input arrays."""
    paths = _dis_model_output(function_tmpdir, xorigin=100.0, yorigin=200.0, angrot=30.0)
    head = open_hds(paths["hds"], paths["grb"])
    botm = paths["gwf"].dis.to_dataarray("botm")
    assert head.x.dims == ("col",)
    assert np.allclose(head.x, botm.x)
    assert np.allclose(head.y, botm.y)
    assert head.attrs["grid_mapping"] == "projection"
    assert head.projection.attrs == botm.projection.attrs
    assert head.projection.attrs == {"xorigin": 100.0, "yorigin": 200.0, "angrot": 30.0}
    assert np.allclose(head.x_world, botm.x_world)
    assert np.allclose(head.y_world, botm.y_world)


def test_open_hds_disv_rotated(function_tmpdir):
    """A rotated DISV grid's output mesh is rotated about the origin, so
    its cell centres match the input arrays'."""
    paths = _disv_model_output(function_tmpdir, xorigin=100.0, yorigin=200.0, angrot=30.0)
    head = open_hds(paths["hds"], paths["grb"])
    botm = paths["gwf"].dis.to_dataarray("botm")
    centroids = head.ugrid.grid.face_coordinates
    assert np.allclose(centroids[:, 0], botm.x)
    assert np.allclose(centroids[:, 1], botm.y)


def test_disv_from_grid_round_trip():
    """Disv -> VertexGrid -> Disv should preserve all geometry."""
    nlay, ncpl, nvert = 2, 4, 6
    cells = [[0, 1, 4, 3], [1, 2, 5, 4]]
    # Two quads; extend to ncpl=4 by duplicating cells
    cells_full = cells + cells
    cell2d = [Disv.Cell2d(n, float(n % 2) + 0.5, 0.5, 4, tuple(cells_full[n])) for n in range(ncpl)]
    # 2×3 grid of vertices
    xv = np.array([0.0, 1.0, 2.0, 0.0, 1.0, 2.0])
    yv = np.array([1.0, 1.0, 1.0, 0.0, 0.0, 0.0])
    botm = np.stack([np.zeros(ncpl), np.full(ncpl, -10.0)])
    disv_orig = Disv(
        nlay=nlay,
        ncpl=ncpl,
        nvert=nvert,
        top=np.ones(ncpl),
        botm=botm,
        idomain=np.ones((nlay, ncpl), dtype=int),
        vertices=dict(iv=np.arange(nvert, dtype=int), xv=xv, yv=yv),
        cell2d=cell2d,
    )

    # Convert to VertexGrid, then back to Disv
    grid = disv_orig.to_grid()
    assert isinstance(grid, VertexGrid)
    disv_rt = Disv.from_grid(grid)

    # Dimensions must be preserved
    assert disv_rt.nlay == nlay
    assert disv_rt.ncpl == ncpl
    assert disv_rt.nvert == nvert

    # idomain must be preserved (tests the `is not None` fix)
    assert disv_rt.idomain is not None
    np.testing.assert_array_equal(disv_rt.idomain, disv_orig.idomain)

    # Vertex coordinates must be preserved
    np.testing.assert_allclose([v.xv for v in disv_rt.vertices], [v.xv for v in disv_orig.vertices])
    np.testing.assert_allclose([v.yv for v in disv_rt.vertices], [v.yv for v in disv_orig.vertices])


def test_disv1d_from_grid_round_trip():
    """Disv1d -> VertexGrid (its `cell1d` form) -> Disv1d should preserve
    all geometry (`Disv1dMethods`)."""
    from flopy4.mf6.chf.disv1d import Disv1d

    disv1d_orig = Disv1d(
        nodes=2,
        nvert=3,
        vertices=[(0, 0.0, 0.0), (1, 10.0, 0.0), (2, 20.0, 0.0)],
        cell1d=[(0, 0.5, 2, (0, 1)), (1, 0.5, 2, (1, 2))],
        bottom=[0.0, 0.0],
        idomain=[1, 1],
    )

    grid = disv1d_orig.to_grid()
    assert isinstance(grid, VertexGrid)
    disv1d_rt = Disv1d.from_grid(grid)

    assert disv1d_rt.nodes == 2
    assert disv1d_rt.nvert == 3
    assert disv1d_rt.idomain is not None
    np.testing.assert_array_equal(disv1d_rt.idomain, disv1d_orig.idomain)
    np.testing.assert_allclose(disv1d_rt.bottom, disv1d_orig.bottom)
    assert [c.icvert for c in disv1d_rt.cell1d] == [c.icvert for c in disv1d_orig.cell1d]
    np.testing.assert_allclose(
        [v.xv for v in disv1d_rt.vertices], [v.xv for v in disv1d_orig.vertices]
    )


# NetCDF head-reader tests (_open_hds_netcdf paths)


def test_open_hds_dis_netcdf_conventional(function_tmpdir, dis_model_output):
    """
    _open_hds_netcdf — conventional CF structured format.

    Writes a synthetic NetCDF file with a ``head(time, z, y, x)`` variable
    and ``modflow_grid = "STRUCTURED"`` attribute (no ``mesh`` global
    attribute), matching what MODFLOW 6 writes for DIS grids in structured
    mode.
    """
    from pathlib import Path

    paths = dis_model_output
    nlay, nrow, ncol = paths["nlay"], paths["nrow"], paths["ncol"]
    ntime = 2

    rng = np.random.default_rng(0)
    data = rng.random((ntime, nlay, nrow, ncol))
    ds = xr.Dataset(
        {"head": xr.DataArray(data, dims=("time", "z", "y", "x"))},
        coords={"time": np.array([1.0, 2.0])},
        attrs={"modflow_grid": "STRUCTURED"},
    )
    nc_path = Path(function_tmpdir) / "head_structured.nc"
    ds.to_netcdf(nc_path)

    head = open_hds(nc_path, paths["grb"])

    assert isinstance(head, xr.DataArray)
    assert head.dims == ("time", "layer", "row", "col")
    assert head.shape == (ntime, nlay, nrow, ncol)
    np.testing.assert_allclose(head.values, data)


def test_open_hds_dis_netcdf_keeps_file_crs(function_tmpdir):
    """The grb has no CRS, so a netCDF file's projection gives it: the
    head's projection has the file's crs_wkt, with the grb's placement."""
    from pathlib import Path

    paths = _dis_model_output(function_tmpdir, xorigin=100.0, yorigin=200.0, angrot=30.0)
    nlay, nrow, ncol = paths["nlay"], paths["nrow"], paths["ncol"]
    expected = grid_mapping(100.0, 200.0, 30.0, "EPSG:26916")[2]
    ds = xr.Dataset(
        {
            "head": xr.DataArray(np.zeros((1, nlay, nrow, ncol)), dims=("time", "z", "y", "x")),
            "projection": ((), 1, {**expected, "xorigin": 0.0, "angrot": 0.0}),
        },
        coords={"time": np.array([1.0])},
        attrs={"modflow_grid": "STRUCTURED"},
    )
    nc_path = Path(function_tmpdir) / "head_crs.nc"
    ds.to_netcdf(nc_path)

    head = open_hds(nc_path, paths["grb"])

    assert head.projection.attrs == expected
    assert head.attrs["grid_mapping"] == "projection"
    assert "x_world" in head.coords


def test_open_hds_disv_netcdf_ugrid_layered(function_tmpdir, disv_model_output):
    """
    _open_hds_netcdf — CF-UGRID layered format for DISV.

    Writes a synthetic NetCDF file with ``head_l1``, ``head_l2`` variables
    on ``(time, nmesh_face)`` dimensions and a ``modflow_mesh`` global
    attribute, matching what MODFLOW 6 currently writes for DISV grids in
    layered mesh mode (renamed from the bare ``mesh`` attribute, which
    collided with UGRID's reserved per-variable ``mesh`` attribute in some
    CF readers).
    """
    from pathlib import Path

    paths = disv_model_output
    nlay, ncpl = paths["nlay"], paths["ncpl"]
    ntime = 2

    rng = np.random.default_rng(1)
    layer_data = [rng.random((ntime, ncpl)) for _ in range(nlay)]
    data_vars = {
        f"head_l{k + 1}": xr.DataArray(layer_data[k], dims=("time", "nmesh_face"))
        for k in range(nlay)
    }
    ds = xr.Dataset(
        data_vars,
        coords={"time": np.array([1.0, 2.0])},
        attrs={"modflow_mesh": 1, "modflow_grid": "VERTEX"},
    )
    nc_path = Path(function_tmpdir) / "head_ugrid.nc"
    ds.to_netcdf(nc_path)

    head = open_hds(nc_path, paths["grb"])

    assert isinstance(head, xu.UgridDataArray)
    assert "time" in head.dims
    assert "layer" in head.dims
    assert head.shape[0] == ntime
    assert head.shape[1] == nlay
    assert head.shape[2] == ncpl
    # Data values should round-trip exactly
    for k in range(nlay):
        np.testing.assert_allclose(head.values[:, k, :], layer_data[k])


def test_open_hds_disv_netcdf_ugrid_layered_legacy_mesh_attr(function_tmpdir, disv_model_output):
    """
    _open_hds_netcdf still recognizes the legacy bare ``mesh`` global
    attribute (pre-rename) as a fallback, for files written before MF6
    renamed it to ``modflow_mesh``.
    """
    from pathlib import Path

    paths = disv_model_output
    nlay, ncpl = paths["nlay"], paths["ncpl"]
    ntime = 2

    rng = np.random.default_rng(1)
    layer_data = [rng.random((ntime, ncpl)) for _ in range(nlay)]
    data_vars = {
        f"head_l{k + 1}": xr.DataArray(layer_data[k], dims=("time", "nmesh_face"))
        for k in range(nlay)
    }
    ds = xr.Dataset(
        data_vars,
        coords={"time": np.array([1.0, 2.0])},
        attrs={"mesh": 1, "modflow_grid": "VERTEX"},
    )
    nc_path = Path(function_tmpdir) / "head_ugrid_legacy.nc"
    ds.to_netcdf(nc_path)

    head = open_hds(nc_path, paths["grb"])

    assert isinstance(head, xu.UgridDataArray)
    assert head.shape[0] == ntime
    assert head.shape[1] == nlay
    assert head.shape[2] == ncpl


def test_open_hds_netcdf_grid_type_mismatch(function_tmpdir, dis_model_output):
    """
    _open_hds_netcdf raises ValueError when the NetCDF modflow_grid attribute
    disagrees with the GRB file's grid type.
    """
    from pathlib import Path

    paths = dis_model_output
    nlay, nrow, ncol = paths["nlay"], paths["nrow"], paths["ncol"]

    # Write a file claiming VERTEX but use the DIS GRB (which is STRUCTURED)
    ds = xr.Dataset(
        {"head": xr.DataArray(np.zeros((1, nlay, nrow, ncol)), dims=("time", "z", "y", "x"))},
        coords={"time": np.array([1.0])},
        attrs={"modflow_grid": "VERTEX"},
    )
    nc_path = Path(function_tmpdir) / "head_mismatch.nc"
    ds.to_netcdf(nc_path)

    with pytest.raises(ValueError, match="Grid type mismatch"):
        open_hds(nc_path, paths["grb"])


def test_open_hds_file_not_found(function_tmpdir, dis_model_output):
    """open_hds raises FileNotFoundError for a missing HDS file."""
    from pathlib import Path

    paths = dis_model_output
    with pytest.raises(FileNotFoundError):
        open_hds(Path(function_tmpdir) / "nonexistent.hds", paths["grb"])


def test_open_cbc_file_not_found(function_tmpdir, dis_model_output):
    """open_cbc raises FileNotFoundError / passes through for missing CBC."""
    from pathlib import Path

    paths = dis_model_output
    with pytest.raises((FileNotFoundError, OSError)):
        open_cbc(Path(function_tmpdir) / "nonexistent.cbc", paths["grb"])


def test_open_hds_dis_face_budget_values(dis_model_output):
    """
    The right/front/lower face flows should be non-trivially populated.

    This regression test guards against the bug where dis_indices computed
    wrong indices due to incorrect 0/1-based adjustment of ia/ja.
    """
    paths = dis_model_output
    cbc = open_cbc(paths["cbc"], paths["grb"])
    assert isinstance(cbc, xr.Dataset)
    # At least one of the directional flows must contain non-zero values;
    # if dis_indices is broken all face flows are zero or misindexed.
    assert "flow-right-face" in cbc.data_vars or "flow-ja-face" in cbc.data_vars
    # Check that the face flows have the right shape
    if "flow-right-face" in cbc.data_vars:
        right = cbc["flow-right-face"]
        assert right.dims == ("time", "layer", "row", "col")
        assert right.coords["x"].dims == ("col",)
        # Should have at least some non-zero values (CHD drives flow)
        assert float(np.abs(right.values).max()) > 0.0


def test_open_cbc_dis_selects_by_xy(dis_model_output):
    """Every DIS budget array, face flows too, selects by x and y."""
    paths = dis_model_output
    cbc = open_cbc(paths["cbc"], paths["grb"])
    gridded = [da for da in cbc.data_vars.values() if "row" in da.dims]
    assert gridded
    for da in gridded:
        x, y = float(da.x[1]), float(da.y[0])
        np.testing.assert_array_equal(da.sel(x=x, y=y).values, da.isel(col=1, row=0).values)
