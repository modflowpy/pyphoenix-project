# todo

## perf

### memory

Need to deduplicate data trees.
Each component should get a view into the root (as far as it's aware) tree
unless it's the root (i.e. simulation) itself, or it's not attached to any
parent context, in which case it's the root of its own tree.

### speed

Need faster dimension resolution.
We know the path from simulation to dis and tdis, no reason to search for it.

## api

### components

I think for access by name we want dict style e.g. `gwf["chd1"]`,
like imod-python does it.

By type, e.g. `gwf.chd`, where it's either a single component,
or a dict by name (or auto-increment index) for multipackages?

## docs

Reproduce flopy3 quickstart.
Keep it minimal, just show an equivalent with the prototype.

More detailed demo notebook.
Compare/contrast implementations and different patterns in
more detail.
