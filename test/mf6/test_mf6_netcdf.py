import numpy as np
import xarray as xr

from flopy4.mf6.netcdf import (
    FILL_DNODATA,
    FILL_FLOAT64,
    FILL_INT64,
    NetCDFModel,
    NetCDFPackage,
    NetCDFParam,
)


def grid_nodata(dims):
    grid = np.full((dims[1], dims[2], dims[3]), FILL_DNODATA, dtype=float)
    return np.repeat(np.expand_dims(grid, axis=0), repeats=dims[0], axis=0)


def layer_nodata(dims):
    layer = np.full((dims[2], dims[3]), FILL_DNODATA, dtype=float)
    return np.repeat(np.expand_dims(layer, axis=0), repeats=dims[0], axis=0)


def test_model_nomesh():
    dims = [2, 4, 3, 2]  # [nper, nlay, nrow, ncol]
    welg_0_q = grid_nodata(dims)
    welg_0_q[0, ...] = np.linspace(0, 1, 24).reshape([4, 3, 2])
    rcha_0_recharge = layer_nodata(dims)
    rcha_0_recharge[1, ...] = np.linspace(1, 2, 6).reshape([3, 2])

    packages = [
        {
            "package_name": "welg_0",
            "package_type": "gwf-wElg",
            "auxiliary": ["concentration"],
            "params": [
                {"name": "aux"},
                {"name": "q", "data": welg_0_q},
            ],
        },
        {
            "package_name": "rcha_0",
            "package_type": "gwf-rcha",
            "params": [
                {"name": "recharge", "data": rcha_0_recharge},
            ],
        },
    ]
    nc_cfg = {
        "modeltype": "gwf6",
        "modelname": "gwFmodel",
        "gridtype": "structured",
        "packages": packages,
    }

    # classmethod to generate and validate model
    nc_model = NetCDFModel.from_dict(nc_cfg, context={"dims": dims})
    meta = nc_model.meta
    assert isinstance(meta, dict)

    # dataset from model instance
    ds = nc_model.to_xarray()
    assert isinstance(ds, xr.Dataset)

    assert ds.attrs["modflow_grid"] == "structured"
    assert ds.attrs["modflow_model"] == "gwf6: gwfmodel"
    assert "mesh" not in ds.attrs
    assert "welg_0_q" in ds
    assert "welg_0_concentration" in ds
    assert np.allclose(ds["welg_0_q"].values, welg_0_q)
    assert np.allclose(ds["welg_0_concentration"].values, FILL_DNODATA)
    assert np.allclose(ds["rcha_0_recharge"].values, rcha_0_recharge)
    assert ds["welg_0_q"].dims == ("time", "layer", "y", "x")
    assert ds["welg_0_concentration"].dims == ("time", "layer", "y", "x")
    assert ds["rcha_0_recharge"].dims == ("time", "y", "x")
    assert ds.sizes["time"] == 2
    assert ds.sizes["layer"] == 4
    assert ds.sizes["y"] == 3
    assert ds.sizes["x"] == 2
    assert len(ds) == 3

    context = {
        "modelname": "gwfmodel",
        "gridtype": "structured",
        "dims": [2, 4, 3, 2],
    }

    for p in packages:
        nc_pkg = NetCDFPackage.from_dict(
            p,
            context=context,
        )
        ds = nc_pkg.to_xarray()
        assert isinstance(ds, xr.Dataset)
        meta = nc_pkg.meta
        assert isinstance(meta, dict)
        nc_pkg = NetCDFPackage.model_validate(meta, context=context)


def test_package_nomesh():
    packages = [
        {
            "package_name": "welg_0",
            "package_type": "gwf-welg",
            "auxiliary": ["concentration", "temperature"],
            "params": [
                {"name": "aux"},
                {"name": "q"},
            ],
        },
    ]

    context = {"modelname": "gwfmodel", "gridtype": "structured", "dims": [1, 1, 1, 1]}

    nc_pkg = NetCDFPackage.from_dict(packages[0], context=context)
    meta = nc_pkg.meta
    assert isinstance(meta, dict)
    nc_pkg = NetCDFPackage.model_validate(meta, context=context)
    ds = nc_pkg.to_xarray()
    assert isinstance(ds, xr.Dataset)

    # assert ds.attrs["modflow_grid"] == "structured"
    # assert ds.attrs["modflow_model"] == "gwf6: gwfmodel"
    assert "mesh" not in ds.attrs
    assert "welg_0_q" in ds
    assert "welg_0_concentration" in ds
    assert "welg_0_temperature" in ds
    assert np.allclose(ds["welg_0_q"].values.ravel(), FILL_DNODATA)
    assert np.allclose(ds["welg_0_concentration"].values, FILL_DNODATA)
    assert np.allclose(ds["welg_0_temperature"].values, FILL_DNODATA)
    assert ds["welg_0_q"].dims == ("time", "layer", "y", "x")
    assert ds["welg_0_concentration"].dims == ("time", "layer", "y", "x")
    assert ds["welg_0_temperature"].dims == ("time", "layer", "y", "x")
    assert ds.sizes["time"] == 1
    assert ds.sizes["layer"] == 1
    assert ds.sizes["y"] == 1
    assert ds.sizes["x"] == 1
    assert len(ds) == 3


def test_param_nomesh():
    params = [
        {"name": "aux", "attrs": {"modflow_iaux": 1}},
        {"name": "q"},
    ]
    context = {
        "modelname": "gwfmodel",
        "gridtype": "structured",
        "package_name": "welg0",
        "package_type": "gwf-welg",
        "dims": [1, 1, 1, 1],
    }

    for p in params:
        nc_param = NetCDFParam.from_dict(p, context=context)
        ds = nc_param.to_xarray()
        assert isinstance(ds, xr.Dataset)
        meta = nc_param.meta
        assert isinstance(meta, dict)
        nc_param = NetCDFParam.model_validate(meta, context=context)


def test_model_mesh():
    dims = [2, 4, 3, 2]  # [nper, nlay, nrow, ncol]
    dis_botm = np.linspace(11, 21, 24)
    npf_k = np.linspace(0, 10, 24)
    welg_0_q = grid_nodata(dims)
    welg_0_q[0, ...] = np.linspace(0, 1, 24).reshape([4, 3, 2])
    rcha_0_recharge = np.linspace(1, 2, 12)
    packages = [
        {
            "package_name": "dis",
            "package_type": "gwf-dis",
            "params": [
                {"name": "delr"},
                {"name": "delc"},
                {"name": "idomain"},
                {"name": "botm", "data": dis_botm},
            ],
        },
        {
            "package_name": "npf",
            "package_type": "gwf-npf",
            "params": [
                {"name": "icelltype"},
                {"name": "k", "data": npf_k},
                {"name": "k22"},
            ],
        },
        {
            "package_name": "welg_0",
            "package_type": "gwf-welg",
            "auxiliary": ["concentration"],
            "params": [
                {"name": "aux"},
                {"name": "q", "data": welg_0_q},
            ],
        },
        {
            "package_name": "rcha_0",
            "package_type": "gwf-rcha",
            "params": [
                {"name": "recharge", "data": rcha_0_recharge},
            ],
        },
    ]
    nc_cfg = {
        "modeltype": "gwf6",
        "modelname": "gwfmodel",
        "gridtype": "structured",
        "attrs": {"mesh": "layered"},
        "packages": packages,
    }

    # classmethod to generate and validate model
    nc_model = NetCDFModel.from_dict(nc_cfg, context={"dims": dims})

    # dataset from model instance
    ds = nc_model.to_xarray()

    assert ds.attrs["modflow_grid"] == "structured"
    assert ds.attrs["modflow_model"] == "gwf6: gwfmodel"
    assert ds.attrs["mesh"] == "layered"
    assert "dis_delr" in ds
    assert "dis_delc" in ds
    assert "rcha_0_recharge" in ds
    assert np.allclose(ds["dis_delr"].values, FILL_FLOAT64)
    assert np.allclose(ds["dis_delc"].values, FILL_FLOAT64)
    assert np.allclose(ds["rcha_0_recharge"].values.ravel(), rcha_0_recharge)
    assert ds["dis_delr"].dims == ("x",)
    assert ds["dis_delc"].dims == ("y",)
    assert ds["rcha_0_recharge"].dims == ("time", "nmesh_face")
    for layer in range(4):
        assert f"dis_idomain_l{layer + 1}" in ds
        assert f"dis_botm_l{layer + 1}" in ds
        assert f"npf_k_l{layer + 1}" in ds
        assert f"npf_k22_l{layer + 1}" in ds
        assert f"npf_icelltype_l{layer + 1}" in ds
        assert f"welg_0_q_l{layer + 1}" in ds
        assert f"welg_0_concentration_l{layer + 1}" in ds
        assert np.allclose(ds[f"dis_idomain_l{layer + 1}"].values, FILL_INT64)
        assert np.allclose(ds[f"dis_botm_l{layer + 1}"].values, dis_botm.reshape([4, 6])[layer, :])
        assert np.allclose(ds[f"npf_k_l{layer + 1}"].values, npf_k.reshape([4, 6])[layer, :])
        assert np.allclose(ds[f"npf_k22_l{layer + 1}"].values, FILL_FLOAT64)
        assert np.allclose(ds[f"npf_icelltype_l{layer + 1}"].values, FILL_INT64)
        assert np.allclose(
            ds[f"welg_0_q_l{layer + 1}"].values,
            welg_0_q.reshape([2, 4, 6])[:, layer, :],
        )
        assert np.allclose(ds[f"welg_0_concentration_l{layer + 1}"].values, FILL_DNODATA)
        assert ds[f"dis_idomain_l{layer + 1}"].dims == ("nmesh_face",)
        assert ds[f"npf_k_l{layer + 1}"].dims == ("nmesh_face",)
        assert ds[f"npf_k22_l{layer + 1}"].dims == ("nmesh_face",)
        assert ds[f"npf_icelltype_l{layer + 1}"].dims == ("nmesh_face",)
        assert ds[f"welg_0_q_l{layer + 1}"].dims == ("time", "nmesh_face")
        assert ds[f"welg_0_concentration_l{layer + 1}"].dims == ("time", "nmesh_face")
    assert ds.sizes["time"] == 2
    assert ds.sizes["nmesh_face"] == 6
    assert ds.sizes["x"] == 2
    assert ds.sizes["y"] == 3
    assert len(ds) == 31


def test_package_mesh():
    packages = [
        {
            "package_name": "npf",
            "package_type": "gwf-npf",
            "params": [
                {"name": "icelltype"},
                {"name": "k"},
                {"name": "k22"},
            ],
        },
        {
            "package_name": "welg_0",
            "package_type": "gwf-welg",
            "auxiliary": ["concentration"],
            "params": [
                {"name": "aux"},
                {"name": "q"},
            ],
        },
        {
            "package_name": "rcha0",
            "package_type": "gwf-rcha",
            "params": [
                {"name": "recharge"},
                {"name": "irch"},
            ],
        },
    ]

    context = {
        "mesh": "layered",
        "modelname": "gwfmodel",
        "gridtype": "structured",
        "dims": [2, 3, 2, 2],
    }
    for p in packages:
        nc_pkg = NetCDFPackage.from_dict(p, context=context)
        ds = nc_pkg.to_xarray()
        assert isinstance(ds, xr.Dataset)
        meta = nc_pkg.meta
        assert isinstance(meta, dict)
        nc_pkg = NetCDFPackage.model_validate(meta, context=context)

        if p["package_type"] == "gwf-npf":
            # TODO: still write model attrs?
            assert len(ds.attrs) == 0
            for layer in range(3):
                assert f"npf_k_l{layer + 1}" in ds
                assert f"npf_k22_l{layer + 1}" in ds
                assert f"npf_icelltype_l{layer + 1}" in ds
                assert np.allclose(ds[f"npf_k_l{layer + 1}"].values, FILL_FLOAT64)
                assert np.allclose(ds[f"npf_k22_l{layer + 1}"].values, FILL_FLOAT64)
                assert np.allclose(ds[f"npf_icelltype_l{layer + 1}"].values, FILL_INT64)
                assert ds[f"npf_k_l{layer + 1}"].dims == ("nmesh_face",)
                assert ds[f"npf_k22_l{layer + 1}"].dims == ("nmesh_face",)
                assert ds[f"npf_icelltype_l{layer + 1}"].dims == ("nmesh_face",)
            assert ds.sizes["nmesh_face"] == 4
            assert len(ds) == 9

        elif p["package_type"] == "gwf-welg":
            # TODO: still write model attrs?
            assert len(ds.attrs) == 0
            for layer in range(3):
                assert f"welg_0_q_l{layer + 1}" in ds
                assert f"welg_0_concentration_l{layer + 1}" in ds
                assert np.allclose(ds[f"welg_0_q_l{layer + 1}"].values, FILL_DNODATA)
                assert np.allclose(ds[f"welg_0_concentration_l{layer + 1}"].values, FILL_DNODATA)
                assert ds[f"welg_0_q_l{layer + 1}"].dims == ("time", "nmesh_face")
                assert ds[f"welg_0_concentration_l{layer + 1}"].dims == ("time", "nmesh_face")
            assert ds.sizes["time"] == 2
            assert ds.sizes["nmesh_face"] == 4
            assert len(ds) == 6

        elif p["package_type"] == "gwf-rcha":
            # TODO: still write model attrs?
            assert len(ds.attrs) == 0
            assert "rcha0_recharge" in ds
            assert "rcha0_irch" in ds
            assert np.allclose(ds["rcha0_recharge"].values, FILL_DNODATA)
            assert np.allclose(ds["rcha0_irch"].values, FILL_INT64)
            assert ds["rcha0_recharge"].dims == ("time", "nmesh_face")
            assert ds["rcha0_irch"].dims == ("time", "nmesh_face")
            assert ds.sizes["time"] == 2
            assert ds.sizes["nmesh_face"] == 4
            assert len(ds) == 2


def test_param_mesh():
    params = [
        {"name": "aux", "attrs": {"layer": 1, "modflow_iaux": 1}},
        {"name": "aux", "attrs": {"layer": 2, "modflow_iaux": 1}},
        {"name": "q", "attrs": {"layer": 1}},
        {"name": "q", "attrs": {"layer": 2}},
    ]
    context = {
        "mesh": "layered",
        "modelname": "gwfmodel",
        "gridtype": "structured",
        "package_name": "welg0",
        "package_type": "gwf-welg",
        "dims": [1, 2, 1, 1],
    }

    for p in params:
        nc_param = NetCDFParam.from_dict(p, context=context)
        ds = nc_param.to_xarray()
        assert isinstance(ds, xr.Dataset)
        meta = nc_param.meta
        assert isinstance(meta, dict)
        nc_param = NetCDFParam.model_validate(meta, context=context)


def test_welg_two_aux_data():
    """Each aux variable gets its own data slice and modflow_iaux, with and
    without a layered mesh."""
    dims = [2, 4, 3, 2]  # [nper, nlay, nrow, ncol]
    aux = np.stack([grid_nodata(dims), grid_nodata(dims)], axis=1)
    aux[0, 0] = 1.0
    aux[0, 1] = 2.0
    package = {
        "package_name": "welg_0",
        "package_type": "gwf-welg",
        "auxiliary": ["a1", "a2"],
        "params": [{"name": "aux", "data": aux}],
    }
    nc_cfg = {"modeltype": "gwf6", "modelname": "m", "gridtype": "structured"}

    ds = NetCDFModel.from_dict(
        {**nc_cfg, "packages": [package]}, context={"dims": dims}
    ).to_xarray()
    for n, name in enumerate(["a1", "a2"]):
        var = ds[f"welg_0_{name}"]
        assert var.attrs["modflow_iaux"] == n + 1
        assert np.allclose(var.values, aux[:, n])

    ds = NetCDFModel.from_dict(
        {**nc_cfg, "attrs": {"mesh": "layered"}, "packages": [package]}, context={"dims": dims}
    ).to_xarray()
    for n, name in enumerate(["a1", "a2"]):
        for k in range(dims[1]):
            var = ds[f"welg_0_{name}_l{k + 1}"]
            assert var.attrs["modflow_iaux"] == n + 1
            assert np.allclose(var.values, aux[:, n, k].reshape(dims[0], -1))


def test_from_model_periods_past_nper_dropped():
    """Period data past NPER is dropped, with a warning."""
    import pytest

    from flopy4.mf6.gwf import Chdg, Dis, Gwf
    from flopy4.mf6.simulation import Simulation
    from flopy4.mf6.utils.time import Time

    sim = Simulation(tdis=Time(perlen=[1.0], nstp=[1], tsmult=[1.0]), name="s")
    gwf = Gwf(parent=sim, dis=Dis(nlay=1, nrow=1, ncol=2), name="m")
    Chdg(parent=gwf, head=np.array([[1.0, 2.0], [3.0, 4.0]]))
    with pytest.warns(UserWarning, match="past NPER"):
        ds = NetCDFModel.from_model(gwf).to_xarray()
    assert ds.sizes["time"] == 1
    assert np.allclose(ds["chd0_head"].values.ravel(), [1.0, 2.0])


def test_split_aux():
    """Period aux splits into one (nper, ...) array per AUXILIARY name."""
    import pytest

    from flopy4.mf6.package import split_aux

    aux = np.arange(12.0).reshape(2, 2, 3)  # (nper, naux, ncpl)
    parts = split_aux(aux, 2)
    assert [p.shape for p in parts] == [(2, 3), (2, 3)]
    assert np.array_equal(parts[1], aux[:, 1])
    # a single auxiliary, with or without the naux axis
    assert split_aux(aux[:, :1], 1)[0].shape == (2, 3)
    assert split_aux(aux[:, 0], 1)[0].shape == (2, 3)
    with pytest.raises(ValueError, match="expected"):
        split_aux(aux, 3)
