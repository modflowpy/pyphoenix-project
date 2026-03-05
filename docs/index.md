# flopy4 / pyphoenix

**flopy4** (code name *pyphoenix*) is a modern Python interface for
[MODFLOW 6](https://www.usgs.gov/software/modflow-6-usgs-modular-hydrologic-model),
the U.S. Geological Survey's modular groundwater-flow simulator.

The library exposes MODFLOW 6 input and output through:

- **Package objects** — Python classes that mirror every MODFLOW 6 package, with
  input data stored as [xarray](https://xarray.dev) Datasets for easy inspection and manipulation.
- **Grid utilities** — structured (`DIS`) and vertex (`DISV`) grid wrappers with
  [xugrid](https://deltares.github.io/xugrid/) support for unstructured-style plotting.
- **Output readers** — `open_hds()` / `open_cbc()` return labelled `xr.DataArray` /
  `xr.Dataset` objects (or their `xugrid` equivalents for DISV models).
- **NetCDF I/O** — read and write CF-compliant and UGRID-mesh NetCDF files accepted
  by MODFLOW 6's extended NetCDF input mode.

## Quicklinks

- {doc}`examples/quickstart` — 10×10 steady-state DIS model with contour + quiver plot
- {doc}`examples/twri` — 3-layer transient benchmark; list, array, and NetCDF inputs
- {doc}`examples/frenchman-flat` — real-world 87×87 DIS model from ScienceBase

## Source

Source code is hosted at
[github.com/modflowpy/pyphoenix-project](https://github.com/modflowpy/pyphoenix-project).
Bug reports and feature requests are welcome via
[GitHub Issues](https://github.com/modflowpy/pyphoenix-project/issues).
