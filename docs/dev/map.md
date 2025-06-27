# FloPy 4 development roadmap

## Phase 1: Minimum Viable Product

Read/write input files, run simulations, get/set data.
Initial deliverable for alpha testing (USGS, Deltares).
Alpha testers include Joeri, Huite, and the core MF6 team.
Release via `pip install ` from github URL of our development sandbox.
Tentative timeframe: July.

- [x] DFN spec to TOML
- [x] xarray/attrs backend
- [x] unified IO framework
- [ ] MF6 input file parser
- [ ] MF6 input file writer
- [ ] code generation from spec
- [ ] minimal docs (quickstart, etc)

## Phase 2: Minimum Marketable Product

Achieve rough feature-parity with 3.x.
Adopt features from e.g. `imod-python`.
Incorporate feedback from alpha testing.
Beta testers include alpha testers and additional volunteers from USGS and Deltares.
Release via `pip install` from github URL of our development sandbox.
Tentative timeframe: October.

- [ ] structured xarray index for topology/geometry-aware selections
- [ ] xarray accessors for cross-cutting concerns (plot, export)
- [ ] xugrid integration for UGRID-compliance (DIS/DISV grids)
- [ ] more extensive docs (converted from old flopy examples)
- [ ] IO optimization (tuning, laziness/concurrency, etc)
- [ ] comprehensive logging and error handling
- [ ] validation framework, model checks
- [ ] command line interface
- [ ] cell inspector
- [ ] unit-awareness

## Phase 3: Rollout

Integrate the product with the existing repository.
Evaluate feature-parity and fill any remaining gaps.
Release via standard channels (PyPI, Conda).
Dial 3.x down to maintenance mode.
Tentative timeframe: January 2026

- [ ] implement 3.x adapters, compare tests/examples
- [ ] finalize 3.x maintenance plan and 4.x release plan
- [ ] finalize MF6 compatibility policy and codegen tooling
