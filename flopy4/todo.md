# todo

## perf

### memory

Need to deduplicate data trees.
Each component should get a view into the root (as far as it's aware) tree
unless it's the root (i.e. simulation) itself, or it's not the root and it
is't attached to a parent context.

### speed

Need faster dimension resolution.
We know the path from simulation to dis and tdis, no reason to search for it.
BFS is ok as a general solution but we should use all the info we have.

## api

### components

I think for access by name we want dict style e.g. `gwf["chd1"]`.

By type, e.g. `gwf.chd`, where it's either a single component,
or a dict for multipackages.

### variables

Store scalars as `DataTree.attrs`?

## docs

Reproduce flopy3 quickstart.
Keep it minimal, just show an equivalent with the prototype.

More detailed demo notebook.
Compare/contrast implementations and different patterns in
more detail.
