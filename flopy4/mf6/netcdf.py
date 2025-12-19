import abc

import numpy as np
import xarray as xr
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from xattree import XatSpec, asdict, get_xatspec

from flopy4.mf6.constants import FILL_DNODATA, FILL_FLOAT64, FILL_INT64
from flopy4.mf6.model import Model
from flopy4.mf6.package import Package
from flopy4.version import __version__


def metadata(attribute, key: str):
    if hasattr(attribute, "metadata"):
        meta = getattr(attribute, "metadata")
        if key in meta:
            return meta[key]
    return None


def _pkgclass(package_name: str) -> Package:
    import flopy4

    mtype, ptype = package_name.lower().split("-")
    if not hasattr(flopy4.mf6, mtype):
        raise AssertionError(f"not a valid mf6 component: {package_name}")
    model = getattr(flopy4.mf6, mtype)
    if not hasattr(model, ptype):
        raise AssertionError(f"not a valid mf6 component: {package_name}")
    module = getattr(model, ptype)
    return getattr(module, ptype.capitalize())


def multi_package(package_name: str) -> bool:
    package = _pkgclass(package_name)
    if hasattr(package, "multi_package"):
        return getattr(package, "multi_package")
    return False


def get_spec(package_name: str) -> XatSpec:
    return get_xatspec(_pkgclass(package_name))  # type: ignore


def dimmap(gridtype: str, dims: list[int]) -> dict:
    _map = {
        "time": dims[0],
        "z": dims[1],
    }
    if gridtype == "structured":
        _map["y"] = dims[2]
        _map["x"] = dims[3]
        _map["nmesh_face"] = dims[2] * dims[3]
    elif gridtype == "vertex":
        _map["nmesh_face"] = dims[2]
    return _map


def lower(d: dict) -> dict:
    return {k.lower(): v.lower() if isinstance(v, str) else v for k, v in d.items()}


# Define an Abstract Base Class (interface)
class NetCDFInput(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def from_dict(cls, meta: dict, context: dict | None):
        """create new instance, validate against schema."""
        pass

    @abc.abstractmethod
    def to_xarray(self) -> xr.Dataset:
        """create xarray dataset."""
        pass

    @property
    @abc.abstractmethod
    def meta(self) -> dict:
        """get meta dictionary property."""
        pass

    @abc.abstractmethod
    def jsonschema(self) -> dict:
        """create xarray dataset."""
        pass


class NetCDFModel(BaseModel, NetCDFInput):
    attrs: "NetCDFModelAttrs"
    packages: list["NetCDFPackage"] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        self._context = __context

    @classmethod
    def from_dict(cls, meta, context=None):
        try:
            if context:
                context = lower(context)
            _meta = NetCDFModel._backfill_meta(meta, context)
            inst = cls.model_validate(_meta, context=context)
            inst._context |= context if context is not None else inst._context
            return inst
        except ValidationError:
            raise

    @classmethod
    def from_model(cls, model: Model, mesh: str | None = None):
        assert hasattr(model, "name")
        assert hasattr(model, "data")

        modeltype = model.__class__.__name__.lower()
        attrs = {"title": f"{model.name.upper()} model input"}
        packages = []
        distype = None

        if mesh is not None and mesh.lower() != "structured":
            attrs["mesh"] = mesh.lower()

        for c in model.children:  # type: ignore
            package = model.children[c]  # type: ignore
            packagetype = package.__class__.__name__.lower()
            distype = packagetype if packagetype.startswith("dis") else distype
            # TODO: auxiliary
            p = {
                "package_name": package.name,
                "package_type": f"{modeltype}-{packagetype}",
                "params": [],
            }
            xatspec = get_xatspec(type(package))
            multi = package.multi_package if hasattr(package, "multi_package") else False
            data = asdict(package)

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

                    p["params"].append({"name": field_name, "data": data[field_name].values})

            if len(p["params"]) > 0:
                packages.append(p)

        dims = [
            model.data.dims["nper"],
            model.data.dims["nlay"],
        ]

        if distype == "dis":
            dims.append(model.data.dims["nrow"])
            dims.append(model.data.dims["ncol"])
            gridtype = "structured"
        elif distype == "disv":
            dims.append(model.data.dims["ncpl"])
            gridtype = "vertex"

        return NetCDFModel.from_dict(
            meta={
                "modeltype": modeltype,
                "modelname": model.name,
                "gridtype": gridtype,
                "attrs": attrs,
                "packages": packages,
            },
            context={"dims": dims},
        )

    def to_xarray(self) -> xr.Dataset:
        import datetime

        dss = []
        meta = self.model_dump(by_alias=True)
        for p in self.packages:
            dss.append(p.to_xarray())

        ds = xr.merge(dss)

        dt = datetime.datetime.now()
        timestamp = dt.strftime("%m/%d/%Y %H:%M:%S")
        meta["attrs"]["source"] = f"pyphoenix {__version__}"
        meta["attrs"]["history"] = f"first created {timestamp}"
        # TODO: conventions, etc

        for a in meta["attrs"]:
            if meta["attrs"][a] is not None:
                ds.attrs[a] = meta["attrs"][a]
        return ds

    @property
    def meta(self):
        """meta property getter."""
        return self.model_dump(by_alias=True)

    def jsonschema(self) -> dict:
        return self.model_json_schema()

    @field_validator("attrs", mode="before")
    @classmethod
    def validate_attrs(cls, v: dict[str, str]) -> dict[str, str]:
        """
        validate model (dataset) scoped attributes dictionary
        """
        v = lower(v)
        return v

    @staticmethod
    def _backfill_meta(meta: dict, context: dict, verbose: bool = True) -> dict:
        _meta = dict(meta)

        if "attrs" not in _meta:
            _meta["attrs"] = {}

        _meta = lower(_meta)
        _meta["attrs"]["modflow_grid"] = _meta["gridtype"].lower()
        _meta["attrs"]["modflow_model"] = (
            f"{_meta['modeltype'].lower()}: {_meta['modelname'].lower()}"
        )

        _packages = []
        for pkg in _meta["packages"]:
            pkgctx = {"mesh": _meta["attrs"]["mesh"]} if "mesh" in _meta["attrs"] else {}
            pkgctx["modelname"] = _meta["modelname"]
            pkgctx["gridtype"] = _meta["gridtype"]
            pkgctx |= context
            _packages.append(NetCDFPackage.from_dict(pkg, context=pkgctx))
        _meta["packages"] = _packages

        return _meta


class NetCDFModelAttrs(BaseModel):
    # order of params dictates when data added to info dict
    mesh: str | None = Field(default=None)
    modflow_grid: str = Field()
    modflow_model: str = Field()

    model_config = ConfigDict(extra="allow")

    @field_validator("mesh", mode="before")
    @classmethod
    def validate_mesh(cls, v: str | None, info: ValidationInfo) -> str | None:
        """
        validate model mesh attribute
        """
        if v is not None:
            v = v.lower()
            if v != "layered":
                raise ValueError("only LAYERED mesh supported")
            info.context["mesh"] = v  # type: ignore
        return v

    @field_validator("modflow_grid", mode="before")
    @classmethod
    def validate_modflow_grid(cls, v: str, info: ValidationInfo) -> str:
        """
        validate model modflow_grid attribute
        """
        v = v.lower()
        dims = info.context.get("dims")  # type: ignore
        if v == "structured":
            if len(dims) != 4:
                raise AssertionError(
                    "expected 4 input dimensions [time, nlay, nrow, ncol]"
                    " for structured discretization: {dims}"
                )
        elif v == "vertex":
            if len(dims) != 3:
                raise AssertionError(
                    "expected 3 input dimensions [time, nlay, ncpl]"
                    " for vertex discretization: {dims}"
                )
        info.context["gridtype"] = v  # type: ignore
        return v

    @field_validator("modflow_model", mode="before")
    @classmethod
    def validate_modflow_model(cls, v: str, info: ValidationInfo) -> str:
        """
        validate model modflow_model attribute
        """
        v = v.lower()
        tokens = v.split(":")
        if len(tokens) != 2:
            raise ValueError(f"invalid modflow_model attribute: {v}")
        modeltype = tokens[0].strip()
        if modeltype[-1].isdigit():
            modeltype = modeltype[:-1]
        info.context["modeltype"] = modeltype  # type: ignore
        info.context["modelname"] = tokens[1].strip()  # type: ignore
        return v


class NetCDFPackage(BaseModel, NetCDFInput):
    package_name: str = Field()
    package_type: str = Field()
    params: list["NetCDFParam"] = Field(default_factory=list)
    auxiliary: list[str] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        self._context = __context

        if len(self.auxiliary) > 0:
            for p in self.params:
                if p.name == "aux":
                    p._context["auxiliary"] = self.auxiliary

    @classmethod
    def from_dict(cls, meta, context):
        try:
            if context:
                context = lower(context)
            _meta = NetCDFPackage._backfill_meta(meta, context)
            inst = cls.model_validate(_meta, context=context)
            inst._context |= context if context is not None else inst._context
            return inst
        except ValidationError:
            raise

    def to_xarray(self) -> xr.Dataset:
        ds = []
        for p in self.params:
            ds.append(p.to_xarray())

        return xr.merge(ds)

    @property
    def meta(self):
        """meta property getter."""
        return self.model_dump(by_alias=True)

    def jsonschema(self) -> dict:
        return self.model_json_schema()

    @field_validator("package_name", mode="before")
    @classmethod
    def validate_package_name(cls, v: str, info: ValidationInfo) -> str:
        """
        validate package_name string
        """
        v = v.lower()
        info.context["package_name"] = v  # type: ignore
        return v

    @field_validator("package_type", mode="before")
    @classmethod
    def validate_package_type(cls, v: str, info: ValidationInfo) -> str:
        """
        validate package_type string [<component>-<subcomponent>]
        """
        v = v.lower()
        assert get_spec(v)
        info.context["package_type"] = v  # type: ignore
        return v

    @field_validator("auxiliary", mode="before")
    @classmethod
    def validate_auxiliary(cls, v: list[str]) -> list[str]:
        """
        validate package auxiliary list
        """
        v = [aux.lower() for aux in v]
        return v

    @staticmethod
    def _backfill_meta(meta: dict, context: dict, verbose: bool = True) -> dict:
        _meta = dict(meta)

        if "package_name" not in _meta or "package_type" not in _meta:
            raise AssertionError(
                "package missing required package_name or package_type attribute(s)."
            )

        auxiliary = _meta.get("auxiliary", None)

        paramctx = dict(context)
        paramctx["package_name"] = _meta["package_name"]
        paramctx["package_type"] = _meta["package_type"]
        if auxiliary is not None:
            paramctx["auxiliary"] = auxiliary

        spec = get_spec(paramctx["package_type"].lower())

        dims = context.get("dims", None)
        mesh = context.get("mesh", None)
        if dims is None:
            raise AssertionError("dimensions are required context")

        def _add_layered_param(p):
            for layer in range(dims[1]):
                p["attrs"]["layer"] = layer + 1
                _params.append(NetCDFParam.from_dict(p, context=paramctx))

        _params = []
        for p in _meta["params"]:
            if "attrs" not in p:
                p["attrs"] = {}

            if p["name"].lower() == "aux" and (auxiliary is None or len(auxiliary) == 0):
                raise AssertionError("AUX parameter requires auxiliary list input.")

            shape = spec.arrays[p["name"]].dims
            assert shape is not None
            gridded = "nodes" in shape or "nlay" in shape

            if not gridded or mesh is None:
                assert "layer" not in p["attrs"]
                if p["name"].lower() == "aux":
                    for i, aux in enumerate(auxiliary):  # type: ignore
                        p["attrs"]["modflow_iaux"] = i + 1
                        _params.append(NetCDFParam.from_dict(p, context=paramctx))
                else:
                    _params.append(NetCDFParam.from_dict(p, context=paramctx))

            else:
                if p["name"].lower() == "aux":
                    for i, aux in enumerate(auxiliary):  # type: ignore
                        p["attrs"]["modflow_iaux"] = i + 1
                        _add_layered_param(p)
                else:
                    _add_layered_param(p)

        _meta["params"] = _params

        return _meta


class NetCDFParam(BaseModel, NetCDFInput):
    name: str = Field()
    shape: list[str] = Field(default_factory=list)
    attrs: "NetCDFParamAttrs"
    encodings: "NetCDFParamEncodings"
    dtype: np.dtype = Field()
    data: np.ndarray | None = None

    # Allow Pydantic to handle non-native types (numpy)
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def model_post_init(self, __context) -> None:
        self._context = __context
        self._context["dimmap"] = dimmap(self._context["gridtype"], self._context["dims"])

    @classmethod
    def from_dict(cls, meta, context):
        try:
            if context:
                context = lower(context)
                # TODO: verify required context
                if (
                    "modelname" not in context
                    or "package_name" not in context
                    or "package_type" not in context
                    or "gridtype" not in context
                    or "dims" not in context
                ):
                    raise AssertionError(
                        "NetCDFParam incomplete context: modelanme, package_name, "
                        "package_type, gridtype and dims are required."
                    )
                context["dimmap"] = dimmap(context["gridtype"], context["dims"])
            _meta = NetCDFParam._backfill_meta(meta, context)
            inst = cls.model_validate(_meta, context=context)
            inst._context |= context if context is not None else inst._context
            return inst
        except ValidationError:
            raise

    def to_xarray(self) -> xr.Dataset:
        meta = self.model_dump(by_alias=True)
        package_name = self._context["package_name"]
        package_type = self._context["package_type"]
        mesh = self._context.get("mesh", None)
        auxiliary = self._context.get("auxiliary", None)
        ptype = package_type.split("-")[1].strip()
        spec = get_spec(package_type)

        ds = xr.Dataset()

        basename = (
            (
                auxiliary[meta["attrs"]["modflow_iaux"] - 1]
                if auxiliary is not None
                else f"aux{meta['attrs']['modflow_iaux']}"
            )
            if meta["name"] == "aux"
            else meta["name"]
        )
        param = (
            basename
            if (mesh is None or "layer" not in meta["attrs"] or meta["attrs"]["layer"] is None)
            else f"{basename}_l{meta['attrs']['layer']}"
        )
        varname = f"{package_name}_{param}" if multi_package(package_type) else f"{ptype}_{param}"

        if "data" in meta and meta["data"] is not None:
            data = meta["data"]
        else:
            dims = [self._context["dimmap"][dim] for dim in meta["shape"]]
            data = np.full(
                dims,
                meta["encodings"]["_FillValue"],
                dtype=meta["dtype"],
            )

        var_d = {varname: (meta["shape"], data)}
        ds = ds.assign(var_d)

        for a in meta["attrs"]:
            if meta["attrs"][a] is not None:
                ds[varname].attrs[a] = meta["attrs"][a]
        for e in meta["encodings"]:
            if meta["encodings"][e] is not None:
                ds[varname].encoding[e] = meta["encodings"][e]

        return ds

    @property
    def meta(self):
        """meta property getter."""
        return self.model_dump(by_alias=True)

    def jsonschema(self) -> dict:
        return self.model_json_schema()

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str, info: ValidationInfo) -> str:
        """
        validate parameter name
        """
        v = v.lower()
        package = info.context.get("package_type")  # type: ignore
        spec = get_spec(package)

        if v not in spec.arrays:
            raise ValueError(f"param {v} not found in package {package}")
        if not metadata(spec.arrays[v], "netcdf"):
            raise ValueError(f"not a netcdf param: '{v}'")
        return v

    @field_validator("shape", mode="before")
    @classmethod
    def validate_shape(cls, v: list[str]) -> list[str]:
        """
        validate parameter shape
        """
        v = [dim.lower() if isinstance(dim, str) else dim for dim in v]
        valid = ["time", "nmesh_face", "z", "y", "x"]
        if not all(dim in valid for dim in v):
            raise AssertionError(f"invalid param shape={v}. Valid dims={valid}.")
        return v

    @field_validator("attrs", mode="before")
    @classmethod
    def validate_attrs(cls, v: dict[str, int | str], info: ValidationInfo) -> dict[str, int | str]:
        """
        validate parameter attributes dictionary
        """
        v = lower(v)
        param = info.data.get("name")
        mesh = info.context.get("mesh")  # type: ignore
        shape = info.data.get("shape")
        assert shape
        gridded = "nodes" in shape or "nlay" in shape
        if gridded and mesh is not None and ("layer" not in v or v["layer"] is None):
            raise AssertionError(f"expected layer attribute for mesh param '{param}'")
        if param is not None and param == "aux" and "modflow_iaux" not in v:
            raise AssertionError("expected modflow_iaux attribute for aux param")
        return v

    @field_validator("encodings", mode="before")
    @classmethod
    def validate_encodings(cls, v: dict[str, int | float | str]) -> dict[str, int | float | str]:
        """
        validate parameter encodings dictionary
        """
        return v

    @field_validator("dtype", mode="before")
    @classmethod
    def validate_dtype(cls, v: np.dtype) -> np.dtype:
        """
        validate parameter dtype
        """
        if not (np.issubdtype(v, np.floating) or np.issubdtype(v, np.integer)):
            raise AssertionError(f"invalid param dtype={v}, expected numpy numeric dtype.")
        return v

    @field_validator("data", mode="before")
    @classmethod
    def validate_data(cls, v: np.ndarray) -> np.ndarray:
        """
        validate parameter data
        """
        return v

    @staticmethod
    def _backfill_meta(meta: dict, context: dict, verbose: bool = True) -> dict:
        _meta = dict(meta)
        param = _meta["name"]
        modelname = context["modelname"]
        mesh = context.get("mesh", None)
        spec = get_spec(context["package_type"])

        if param not in spec.arrays:
            raise ValueError(f"param {param} not found in package {context['package_type']}")

        if "attrs" not in _meta:
            _meta["attrs"] = {}
        if "encodings" not in _meta:
            _meta["encodings"] = {}

        # add long_name to parameter attributes
        _meta["attrs"]["long_name"] = metadata(spec.arrays[param], "longname")

        def _structured_shape(dfn_shape):
            shape = ["time"] if "nper" in dfn_shape else []
            if "nodes" in dfn_shape:
                shape += ["z", "y", "x"]
            elif "ncpl" in dfn_shape:
                shape += ["y", "x"]
            else:
                if "nlay" in dfn_shape:
                    shape.append("z")
                if "nrow" in dfn_shape:
                    shape.append("y")
                if "ncol" in dfn_shape:
                    shape.append("x")
            return shape

        def _mesh_shape(dfn_shape):
            shape = ["time"] if "nper" in dfn_shape else []
            if (
                "nodes" in dfn_shape
                or "ncpl" in dfn_shape
                or ("nrow" in dfn_shape and "ncol" in dfn_shape)
            ):
                shape.append("nmesh_face")
            elif "nrow" in dfn_shape:
                shape.append("y")
            elif "ncol" in dfn_shape:
                shape.append("x")
            return shape

        # dtype
        _meta["dtype"] = spec.arrays[param].dtype
        if np.issubdtype(spec.arrays[param].dtype, np.floating):
            _meta["encodings"]["_FillValue"] = (
                FILL_DNODATA if metadata(spec.arrays[param], "block") == "period" else FILL_FLOAT64
            )
        elif np.issubdtype(spec.arrays[param].dtype, np.integer):
            _meta["encodings"]["_FillValue"] = (
                # FILL_DNODATA  # TODO: FILL_INODATA
                FILL_INT64
            )

        # modflow_input internal attribute
        ptype = context["package_type"].split("-")[1].strip()
        _meta["attrs"]["modflow_input"] = (
            f"{modelname}/{context['package_name']}/{param}"
            if multi_package(context["package_type"])
            else f"{modelname}/{ptype}/{param}"
        )

        # data dims
        _meta["shape"] = (
            _mesh_shape(spec.arrays[param].dims)
            if mesh is not None
            else _structured_shape(spec.arrays[param].dims)
        )

        # optional data
        if "data" in _meta:
            dims = [context["dimmap"][dim] for dim in _meta["shape"]]
            nval = np.prod(dims)

            if "layer" in _meta["attrs"]:
                data = _meta["data"]
                layer = _meta["attrs"]["layer"] - 1
                if data.size == nval * context["dimmap"]["z"]:
                    # provided data is for full grid
                    s = dims
                    if "nodes" in spec.arrays[param].dims:  # type: ignore
                        if _meta["shape"][0] == "time":
                            s.insert(1, context["dimmap"]["z"])
                            _meta["data"] = data.reshape(s)[:, layer, :]
                        else:
                            s.insert(0, context["dimmap"]["z"])
                            _meta["data"] = data.reshape(s)[layer, :].ravel()
                    elif "nlay" in spec.arrays[param].dims:  # type: ignore
                        s.insert(0, context["dimmap"]["z"])
                        _meta["data"] = data.reshape(s)[layer, :].ravel()
                else:
                    # assume provided data is correctly formatted
                    pass

            else:
                data = _meta["data"]
                assert data.size == nval
                _meta["data"] = data.reshape(dims)

        return _meta


class NetCDFParamAttrs(BaseModel):
    modflow_input: str = Field()
    modflow_iaux: int | None = Field(default=None)
    layer: int | None = Field(default=None)

    model_config = ConfigDict(extra="allow")

    @field_validator("modflow_input", mode="before")
    @classmethod
    def validate_modflow_input(cls, v: str, info: ValidationInfo) -> str:
        """
        validate parameter modflow_input attribute
        """
        v = v.lower()
        modelname = info.context.get("modelname")  # type: ignore
        if v.split("/")[0] != modelname:
            raise ValueError(
                f'modflow_input attribute "{v}" does not match dataset modelname "{modelname}")'
            )
        return v

    @field_validator("modflow_iaux", mode="before")
    @classmethod
    def validate_modflow_iaux(cls, v: int, info: ValidationInfo) -> int:
        """
        validate parameter modflow_iaux attribute
        """
        return v

    @field_validator("layer", mode="before")
    @classmethod
    def validate_layer(cls, v: int, info: ValidationInfo) -> int:
        """
        validate parameter layer attribute
        """
        dims = info.context.get("dims")  # type: ignore
        if v is not None and v > dims[1]:
            raise ValueError(f"param layer attribute value {v} exceeds grid k")
        return v


class NetCDFParamEncodings(BaseModel):
    fill: float = Field(alias="_FillValue")

    model_config = ConfigDict(extra="allow")

    @field_validator("fill", mode="before")
    @classmethod
    def validate_fill(cls, v: float, info: ValidationInfo) -> float:
        """
        validate parameter fill (_FillValue) encoding attribute
        """
        return v
