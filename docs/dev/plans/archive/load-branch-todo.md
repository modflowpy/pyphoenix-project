# TODO

outstanding work items

- [ ] migrate dimension resolution from xattree
- [ ] migrate parent/child binding from xattree
   - [ ] create `ParentSettingDict` class in `flopy4/mf6/dimensions.py`
   - [ ] auto-set parent references on dict assignment
   - [ ] update `Gwf.__attrs_post_init__()` to wrap `packages` dict
   - [ ] update `Simulation.__attrs_post_init__()` to wrap `models` dict
- [ ] migrate data tree conversion from xattree
- [ ] xattree refactor consolidating above?
- [ ] data tree caching
- [ ] attrs -> pydantic
- [ ] mf6 module generation
- [ ] structural validation framework (components)
- [ ] value validation (ranges, consistency, etc)
- [ ] documentation hosted online
- [ ] user guide (getting started)
- [ ] API reference documentation
- [ ] example notebook gallery
- [ ] create advanced tutorials
- [ ] create developer guide
- [ ] flopy3 -> flopy4 conversion guide/script?
- [ ] nice component string representations
- [ ] complete WriteContext with all options
- [ ] support per-component write configuration
- [ ] support external files
- [ ] CLI interface: validate, run, convert, inspect, etc
- [ ] structuring lazy Dask arrays (lazy loading for large models)
- [ ] support out-of-core computation
- [ ] support chunking configuration
- [ ] add big data/model examples
- [ ] NetCDF read/write working
- [ ] xugrid integration functional
- [ ] larger-than-memory models with Dask
- [ ] performance benchmarks against flopy3
- [ ] self-reproducing objects
- [ ] input file linting/validation
