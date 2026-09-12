# FloPy 4 development roadmap

## Milestones

### Demo

Limited set of core functionality, such as:

- object model, data model, user-facing APIs
- IO framework and ASCII file loading/writing
- constructing, running, modifying simulations

Design and implementation are provisional. Implementation may take shortcuts, e.g. components hand-written instead of generated from the DFN specification.

Release to demo participants via `pip install` from github URL.

### MVP

All core functionality. Components generated from the DFN spec. Functionality over performance/polish.

Release to initial USGS and Deltares testers via `pip install ` from github URL. Begin alpha versioning.

### MMP

All core and most peripheral functionality, and may involve:

- Achieving rough feature-parity with 3.x
- Adopting features from e.g. `imod-python`
- Incorporating feedback from user testing
- Refactoring and performance optimization
- Adapting 3.x documentation and examples
- Comprehensive testing and evaluation
- Finalizing maintenance/release plans
- Finalizing MF6 version support plan

Release to wider test audience at USGS and Deltares via `pip install` from github URL. Begin beta versioning.

### GA

Feature-parity with 3.x. Integrated into existing repository. Generally available via standard channels (PyPI, Conda).

3.x enters maintenance-only mode for a limited time after which support will be dropped and all effort moved to 4.x.
