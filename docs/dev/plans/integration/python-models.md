# Python-based models

Extending flopy4 beyond MF6 run as a subprocess: to MF6 in process (through
modflowapi or XMI), and to modelling codes written in Python, such as
pywatershed and timflow. From Feb 2026, when flopy4 still used xattree; the
full draft, with sketch code, is on the `dev-plans-full` branch.

## The idea

flopy4 has a generic layer (`flopy4/spec.py`: field factories, dimensions,
the attrs ↔ xarray conversion) under an MF6 overlay (`flopy4/mf6`: blocks,
DFN metadata, the component registry, file IO). Other codes could reuse the
generic layer with overlays of their own:

- **MF6 through modflowapi/XMI:** the same components and input files, run
  in process with runtime access. No new components, the same engine (so
  results are easy to check), and immediately useful for monitoring,
  optimisation and coupling. The obvious first case; see
  [`modflowapi.md`](modflowapi.md).
- **pywatershed (PRMS):** its own components (parameters, processes), its
  own metadata (`prms_name`, units) and dimensions (`nhru`, `nsegment`),
  run by Python calls, with file IO optional.
- **timflow:** the same pattern, lower priority.

## Design

- **Executors.** A small `Executor` interface (subprocess, modflowapi, a
  Python callable), registered per component type, with
  `Simulation.run(executor=...)` defaulting to the subprocess, so existing
  code doesn't change.
- **Overlays.** Each code adds its own field metadata and base classes on
  top of the generic layer, as MF6 adds `block`. Each owns its dimension
  names; converters map between them.
- **IO is optional.** Python codes are typically used in memory. Files
  (native formats, or JSON/TOML) are for reproducibility.
- **Packages.** `flopy4/<code>/`, in this repo at first, behind extras
  (`flopy4[pywatershed]`).

Alternatives:

- **Separate packages** (`flopy4-pywatershed`): looser coupling and
  independent releases, but harder to share machinery. Possible later.
- **Converters only**, without component classes: less code, but no
  shared specification, xarray views or IO.
- **Entry-point plugins:** lets others add codes, but is harder to keep
  consistent. Possible later.

## Order

1. The executor interface, with the subprocess executor as today's
   behaviour.
2. modflowapi / XMI, validated against subprocess runs.
3. pywatershed: package, metadata, a first set of components, converters to
   and from pywatershed objects, a Python executor.
4. A guide to adding a code.

## Open questions

- Results as code-specific objects, xarray, or the code's native objects
  (probably all three, through converters).
- Testing without the external packages: mocks in CI, optional integration
  tests.
- Pinning the underlying packages' versions through the extras.
- Executors vs. the explicit XMI classes in [`modflowapi.md`](modflowapi.md).
