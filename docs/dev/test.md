# FloPy 4 testing plan

- [x] Reproduce the FloPy3 quickstart
- [x] Hand-write a small number of programmatically defined models, patterned after simple FloPy3 and MF6 test cases. Only limited simulations at first (e.g. just GWF), until code generation is implemented.

- [ ] Set up CI test harness to compare results of simulations written by FloPy3/4. Reuse patterns in MF6 tests: comparisons and/or snapshots. Catalog and resolve differences in simulation output as they are discovered.

- [x] Set up load tests with the models available via the devtools [models API](https://modflow-devtools.readthedocs.io/en/latest/md/models.html).

- [ ] Set up round-trip load/write tests with the same set of models.

- [ ] Characterize non-functional differences between input files written by flopy 3/4.

- [ ] Adapt FloPy3 autotests and MF6 examples to flopy4
