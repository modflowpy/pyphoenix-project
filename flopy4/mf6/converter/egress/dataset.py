import numpy as np
import xarray as xr
import xattree

from flopy4.mf6.constants import FILL_DNODATA, FILL_FLOAT64, FILL_INT32, FILL_INT64
from flopy4.mf6.model import Model
from flopy4.mf6.package import Package


# TODO: longname, auxiliary, encodings (fill)
def xarray_flat(dt: xr.DataTree, mesh_type: str | None = None):
    mesh_type = mesh_type.lower() if mesh_type is not None else None
    model = dt.attrs["host"]  # type: ignore
    assert isinstance(model, Model)

    mname = model.name  # type: ignore
    mtype = model.__class__.__name__.lower()
    nlay = model.data.dims["nlay"]  # type: ignore

    # set grid_type # TODO dis vs disv child?
    if "nrow" in model.data.dims and "ncol" in model.data.dims:  # type: ignore
        grid_type = "structured"
    elif "ncpl" in model.data.dims:  # type: ignore
        grid_type = "vertext"
    else:
        pass  # raise?

    def _dims(shape, layer=False):
        dimmap = {
            "time": model.data.dims["nper"],
            "z": model.data.dims["nlay"],
            "y": model.data.dims["nrow"],
            "nmesh_face": model.data.dims["ncpl"],
            "x": model.data.dims["ncol"],
        }

        shp = list(shape)
        if layer:
            idx = 1 if shape[0] == "time" else 0
            shp.insert(idx, "z")
        return [dimmap[s] for s in shp]

    def _encode(varname, shape, dataset):
        if dataset[varname].dtype == np.float64:
            if "time" in shape:
                dataset[varname].encoding["_FillValue"] = FILL_DNODATA
            else:
                dataset[varname].encoding["_FillValue"] = FILL_FLOAT64
        elif dataset[varname].dtype == np.int64:
            dataset[varname].encoding["_FillValue"] = FILL_INT64
        elif dataset[varname].dtype == np.int32:
            dataset[varname].encoding["_FillValue"] = FILL_INT32
        return dataset

    def _add_gridvar(field_name, package, multi, data, dataset):
        ptype = package.__class__.__name__.lower()
        shape = ["time"] if "nper" in data[field_name].dims else []
        if "nodes" in data[field_name].dims:
            shape += ["z", "y", "x"]
        elif "ncpl" in data[field_name].dims:
            shape += ["y", "x"]
        else:
            if "nlay" in data[field_name].dims:
                shape.append("z")
            if "nrow" in data[field_name].dims:
                shape.append("y")
            if "ncol" in data[field_name].dims:
                shape.append("x")
        if multi:
            varname = f"{package.name}_{field_name}"
            mf6_input = f"{mname}/{package.name}/{field_name}"
        else:
            varname = f"{ptype}_{field_name}"
            mf6_input = f"{mname}/{ptype}/{field_name}"

        var_d = {varname: (shape, data[field_name].values.reshape(_dims(shape)))}
        dataset = dataset.assign(var_d)
        dataset[varname].attrs["modflow_input"] = mf6_input
        dataset = _encode(varname, shape, dataset)

        return dataset

    def _add_layered_gridvars(field_name, package, multi, data, dataset):
        ptype = package.__class__.__name__.lower()
        shape = ["time"] if "nper" in data[field_name].dims else []
        if (
            "nodes" in data[field_name].dims
            or "ncpl" in data[field_name].dims
            or ("nrow" in data[field_name].dims and "ncol" in data[field_name].dims)
        ):
            shape.append("nmesh_face")
        elif "nrow" in data[field_name].dims:
            shape.append("y")
        elif "ncol" in data[field_name].dims:
            shape.append("x")
        if multi:
            mf6_input = f"{mname}/{package.name}/{field_name}"
            basename = f"{package.name}_{field_name}"
        else:
            mf6_input = f"{mname}/{ptype}/{field_name}"
            basename = f"{ptype}_{field_name}"

        if (
            data[field_name].dims == ("nper", "nodes")
            or "nlay" in data[field_name].dims
            or "nodes" in data[field_name].dims
        ):
            for layer in range(nlay):
                varname = f"{basename}_l{layer + 1}"
                if data[field_name].dims == ("nper", "nodes"):
                    var_d = {
                        varname: (
                            shape,
                            data[field_name].values.reshape(_dims(shape, True))[:, layer, :],
                        )
                    }
                elif "nlay" in data[field_name].dims:
                    var_d = {varname: (shape, data[field_name].values[layer, :, :].flatten())}
                elif "nodes" in data[field_name].dims:
                    var_d = {
                        varname: (
                            shape,
                            data[field_name].values.reshape(_dims(shape, True))[layer, :].flatten(),
                        )
                    }
                dataset = dataset.assign(var_d)
                dataset[varname].attrs["modflow_input"] = mf6_input
                dataset[varname].attrs["layer"] = layer + 1
                dataset = _encode(varname, shape, dataset)
        else:
            varname = basename
            var_d = {varname: (shape, data[field_name].values.reshape(_dims(shape)))}
            dataset = dataset.assign(var_d)
            dataset[varname].attrs["modflow_input"] = mf6_input
            dataset = _encode(varname, shape, dataset)
        return dataset

    ds = xr.Dataset()
    ds.attrs["modflow_model"] = f"{mtype}6: {mname}"
    ds.attrs["modflow_grid"] = f"{grid_type}"
    if mesh_type is not None:
        ds.attrs["mesh"] = mesh_type

    for c in model.children:  # type: ignore
        package = model.children[c]  # type: ignore
        assert isinstance(package, Package)
        xatspec = xattree.get_xatspec(type(package))

        if hasattr(package, "multi_package"):
            multi = package.multi_package
        else:
            multi = False

        data = xattree.asdict(package)

        for block_name, block in package.dfn.blocks.items():
            if block_name != "griddata" and block_name != "period":
                continue
            for field_name in block.keys():
                if (
                    data[field_name] is None
                    or field_name not in xatspec.arrays
                    or not hasattr(xatspec.arrays[field_name], "metadata")
                    or "netcdf" not in xatspec.arrays[field_name].metadata  # type: ignore
                    or not xatspec.arrays[field_name].metadata["netcdf"]  # type: ignore
                ):
                    continue

                if mesh_type is None:
                    ds = _add_gridvar(field_name, package, multi, data, ds)
                elif mesh_type == "layered":
                    ds = _add_layered_gridvars(field_name, package, multi, data, ds)

    return ds
