# FloPy 4 testing plan

## Phase 1: MVP testing

Reproduce the FloPy3 quickstart.

Hand-write a small number of programmatically defined models, patterned after simple FloPy3 and MF6 test cases. Support only limited simulations at first (e.g. just GWF), until code generation is implemented.

Set up CI test harness to compare results of simulations written by FloPy3 and the product. Reuse patterns in MF6 tests: comparisons and/or snapshots. Catalog and resolve differences in simulation output as they are discovered. Begin with the set of [MODFLOW 6 test models](https://github.com/MODFLOW-ORG/modflow6-testmodels) since the input files are readily available.

Alpha testers provide feedback.

## Phase 2: MMP testing

Adapt FloPy3 Python tests and MF6 examples to the product. Exhaustively characterize differences (API and behavior) between FloPy3 and the product, including cosmetic differences in input files written by the two systems.

Beta testers provide feedback.
