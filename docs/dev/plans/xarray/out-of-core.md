# Out-of-core data

How flopy4 gets from partial dask support to FUNC-8: building, writing and
reloading a model larger than the machine's memory. Written 2026-11-04.
Measurements are from `develop` (`8d25e4b7`), and the scripts are in
[`data/out-of-core/`](data/out-of-core/).

"Chunk" here always means a dask or file chunk. "Block" is MF6's word, so this
doc doesn't use it for dask's.

## Decisions

Decided 2026-11-04.

- **FUNC-8 stays at MMP.** The target is a 1 km, 10-layer CONUS model:
  create, write and reload. Running it is MF6's concern, not FUNC-8's.
- **Writing streams.** Peak memory depends on chunk size, not model size.
- **`load()` stays eager; `load(chunks=...)` is lazy.** See
  [Load modes](#load-modes).
- **Lists are in scope,** as well as arrays.
- **A faster text writer is optional, through `xarray-extras`.** We don't write
  a kernel of our own, since flopy4 is pure Python.
- **PR #66 isn't revived.** It's a benchmark of code that no longer exists. See
  [PR #66](#pr-66).

The target's size: CONUS's bounding rectangle at 1 km is roughly 4,600 x 2,900
cells, about 13M per layer and 133M in all, so one float64 array is about 1 GB.

## Where things stand

Each operation ran on lazy arrays that count their chunks as they're computed.
Peaks are `tracemalloc`'s, for `k` of 20 MB or less, on the synchronous
scheduler.

| Operation | Result | Where |
|---|---|---|
| Construct griddata, or period arrays as a dict | stays lazy | |
| `to_xarray`, griddata | stays lazy | |
| Open/close text, a chunk per layer | **bounded:** about 3 MB from 4 to 64 layers | |
| Inline text | about 5x `k`, growing with `nlay`: the macro buffers its output | `macros.jinja:51` |
| Binary | about 2x `k`, growing with `nlay` | `external.py:497` |
| Flat `(nodes,)` arrays | merged into one chunk, so no better than numpy (130 MB vs. 121 MB) | `filters.py:199` |
| Chunks spanning 4 layers | each computed 4 times (96 computes of 24 chunks) | the layer loop in `macros.jinja` |
| `to_xarray`, period arrays | computes everything, though its docstring says it stays lazy | `period_arrays.py:247` |
| NetCDF | computes everything | `netcdf.py:294`, `period_arrays.py:254` |
| Dense `(nper, ...)` construct | computes every period | `period_arrays.py:169` |
| WELG write | computes everything twice | `all_nodata` |

Other gaps:

- Lazy and numpy writes differ in bytes: numpy wrote `k` on one 18 MB line,
  dask a line per row.
- A lazy constant is never written `CONSTANT`.
- `check_grid_periods` skips lazy blocks.
- One eager array sets the memory floor. Scalar `icelltype=0` under open/close
  took the peak from about 3 MB to 118 MB.
- Construction peaks around 113 MB for 960K cells, whatever the array type. If
  that's linear, 133M cells needs about 15 GB before any data is touched. It
  isn't traced yet; the grid is the suspect.
- From reading the code, not measured: loading is always eager (#516), and list
  data has no lazy path.

Tests missed this because they check that a type stays lazy, and
`benchmarks/profile/test_chunked.py` measures time. Its docstring, and those
of `array2chunks` and `_wrap_array`, say more than the code does.

## PR #66

Its `flopy4/xarray_jinja` is gone. What it found has landed: streaming as
`array2chunks`, the benchmark as `test_chunked.py`, and "binary past a size" as
`binary_threshold`.

One thing was lost. Its template looped over chunks at the top level, so it
really streamed. Ours goes through a macro, which is why inline writes don't.

## Design

### Laziness in the representation

The rule goes in [`representation.md`](representation.md#laziness): any
variable may be lazy, and each consumer states whether it preserves that,
computes once, or computes on request. In [`overview.md`](overview.md)'s jobs,
lazy `dense()` is job C and chunk-aware encoders are job D.

### One seam

Replace the three dask checks (`hasattr(.data, "blocks")`, `_is_dask`,
`isinstance_of(value, "dask.array.core", "Array")`) with one module: `is_lazy`
and ordered chunk iteration. dask stays optional. Test the seam with a small
lazy array that isn't dask's.

### Streaming

Macros buffer: Jinja joins a macro's whole output into one string before
returning it. A template loop at the top level streams through
`template.generate`.

`stream_prototype.py` swaps the template in memory for the `internal` case, with
the layer fixed at 0.32 MB:

| `nlay` | Current peak | Streaming peak | Bytes identical |
|---|---|---|---|
| 4 | 6.5 MB | 3.2 MB | yes |
| 16 | 25.6 MB | 3.5 MB | yes |
| 64 | 101.6 MB | 3.6 MB | yes |

Time is no worse (1.17 s vs. 1.08 s at 64 layers).

- **Arrays:** move the array logic out of `macros.jinja` into a Python
  generator, and have `blocks.jinja` loop over its pieces. Scalars and records
  stay on the macros.
- **Lists:** `data2lines` builds one string on purpose, as it's faster than a
  Jinja loop per row. A generator joining batches of rows should keep most of
  that. Not tested yet.
- **Chunk order:** text needs C order. Compute a band of layers that share
  chunks at once, then emit its layers, so a chunk spanning layers is computed
  once. Peak is then one band. Fixed-size pieces do the same for flat arrays.
- **`dumps()`** returns one string by design, and stays as it is.

Numpy users gain too, since a flat `k` peaks at about 16x the array today.
Writing those arrays a line per row changes their bytes, so snapshot tests need
updating. MF6 should read them the same.

### One pass over the values

Anything that needs values shares the streaming pass, with no extra computes:
constant detection, DNODATA checks and active cells (`check_grid_periods`).
Errors from lazy data then surface at write. A lazy constant can't be known
before the pass, so it stays `INTERNAL` unless the writer can buffer one chunk
and find the whole array constant; decide this when implementing, and record it
in the fidelity table.

### `dense()` is lazy

Export phase 2 hasn't built it yet, so build it lazily now: fill-forward can
reference the same array, and periods stack without computing. Retrofitting that
costs more. The current `period_arrays.dense` (`np.full`, `np.asarray`) is what
`to_xarray` and NetCDF materialize through.

### Formats for scale

Binary and NetCDF are the formats for scale, and inline text only needs to be
correct.

- **Binary:** write a chunk at a time, without `tobytes` on the whole array.
- **NetCDF:** keep dask through `NetCDFModel.from_model`, which also gives
  [`overview.md`](overview.md) step 5 another reason. Don't use
  `np.asarray`/`dense`.
- **Size-based default:** decide whether a default `binary_threshold` belongs
  here, as #49 suggested. It changes what files a model gets, so it's opt-in
  until decided.

### A faster text writer

`format_bench.py`, on 1M full-precision floats, each read back and checked:

| Formatter | Time | vs. current default | Bytes per value | Exact? |
|---|---|---|---|---|
| `repr` (current default) | 0.363 s | 1.0x | 20.4 | yes |
| `%.6e` by `savetxt` (current `float_precision`) | 0.187 s | 1.9x | 13.0 | no |
| kernel, `%.6e`, 1 thread | 0.179 s | 2.0x | 13.0 | no |
| kernel, `%.16e`, 1 thread | 0.235 s | 1.5x | 23.0 | yes |
| kernel, `%.16e`, 4 threads | 0.061 s | 5.9x | 23.0 | yes |
| kernel, `%.16e`, 16 threads | 0.036 s | 10.1x | 23.0 | yes |
| kernel, `%.6e`, 4 threads | 0.048 s | 7.6x | 13.0 | no |
| `repr` in 4 threads (control) | 0.328 s | 1.1x | 20.4 | yes |
| pandas `to_csv`, `float_format=None` | 0.885 s | 0.4x | 20.4 | yes |

The speed comes from threads, since the C kernel releases the GIL. Giving up
precision adds little speed, though the files are about 40% smaller. So there
are two settings:

- **`float_precision`** already covers precision (FUNC-17).
- **An engine option,** with `text_engine="fast"` as a working name, picks the
  formatter. It's an optional extra.

The pipeline is: read chunks in order, format on a thread pool, write in order,
with a limit on chunks in flight. That limit is the memory bound.

Public `xarray_extras.csv.to_csv` takes only a path, which suits open/close files.
Inline writes need its private `xarray_extras.kernels`, so pin the version and
test against it. Check first: whether it's maintained, its Windows, macOS and
conda-forge builds, and the speedup on real models. `%.16e` differs in text from
`repr`, so output is logically equal, not text-equal.

### Load modes

This is what `load` does with an array in an external file. Inline arrays have
to be parsed anyway, so they're eager in every mode.

| | Eager (default) | `chunks=` | flopy3 |
|---|---|---|---|
| Load | reads every file | records the file | records array files, reads lists unless `lazy_io` |
| `npf.k` is | numpy | a lazy array | an `MFArray`, whose `.array` is numpy |
| Later accesses | in memory | computes on request | reads the file again, with no cache |
| `npf.k[0] = 5` | works | fails; assign a new array | |
| Bad or missing file | error at load | error at first compute | array: error at first access |
| Larger than memory | no | yes | array by array |

If the external files are larger than available memory, eager `load` warns and
suggests `chunks=`. Reserve the keyword in Track B now, so testers' code doesn't
have to change.

We don't add a read-on-first-touch mode with a cache, as #516 first suggested.
It's a third behaviour to test, it doesn't help FUNC-8, and `chunks=` already
gives its main gain: writing unchanged arrays back without reading them. Reconsider
if slow loads become a complaint.

The deferred reader is an xarray `BackendArray`, so #516 and #368
(`engine="mf6"`) share it, built on the `OpenClose` object in the external-ref
work. Binary files can use `np.memmap`.

### Lists

Lists follow arrays, with a period as the natural chunk.

- **Row counts:** `maxbound` comes from `max(len(rows))` across periods
  (`package.py:237`), so lazy rows must know their length. A binary file's size
  gives that without reading it. A text file takes one line-counting pass.
- **Access:** a lazy list reads one period on access, and is read-only. A period
  too big for memory also needs row batches.
- **Binary writes:** `_binary_records` builds Python rows first
  (`external.py:518`). Go straight from columns.
- **User-built lists:** per-period tables of known length, designed together
  with the representation's sparse `entry` table.
- **Scale format:** binary, as MF6 NetCDF doesn't cover list data. Rows with
  `boundname` or time-series names can't be binary, so they stay text.

### Hazards

- **Overwriting its own source.** A lazy load then `sim.write()` to the same
  workspace truncates the file being read. Write to a temp file and replace it
  atomically. An open memmap will likely block the replace on Windows.
- **Hashing forces a read.** `array_hash` and `_equal` both call `np.asarray`.
  Check whether a reference is unchanged by identity first, then skip the write
  or copy the file.
- **A source file changing after load.** Record size and mtime when deferring,
  and raise if they differ on read. Silently mixing old and new data is worse
  than an error. The compat layer re-reads instead, as flopy3 does.

## flopy3 compatibility

From `flopy3_lazy.py`, on flopy 3.11.0 and a small model, logging each external
file opened:

| Step | `lazy_io=False` (default) | `lazy_io=True` |
|---|---|---|
| Load: arrays, text or binary | not read | not read |
| Load: lists | read | not read |
| Each `.array` access | reads the file again | same |
| Each list `get_data()` | reads the file again | same |
| Type returned | numpy | numpy |
| Edit an array file after load | next access sees it | same |
| Load with array and list files missing | succeeds; array access raises later | same |

`lazy_io` only turns off `verify_data` and `auto_set_sizes`. Arrays defer
regardless.

After `set_sim_path`, both modes wrote the external data inline, with no external
files in the new directory. The log caught no read during that write, so where
the values came from is unexplained. Writing back to the same workspace wasn't
tested.

Against an eager default, flopy3 code would notice three things: a load with a
missing array file now fails, later accesses don't see file edits, and large
external arrays may not fit in memory. No separate mode is needed:

- **`MFSimulation.load()` in the compat layer** defaults to deferred arrays.
- **`.array`** computes on each access, which is flopy3's no-cache behaviour.
- **`lazy_io=True`** is accepted there and defers lists too. The integration plan
  already deprecates it in 3.x.

That depends on I2 ([`replacing-flopy-mf6.md`](../integration/replacing-flopy-mf6.md)).
[`aliases-and-codemod.md`](../integration/aliases-and-codemod.md) leans to option
(a), raising with a hint on `.array`, and then only the warning and a migration
note remain. Native flopy4's earlier error and eager memory use go in Track E's
classification as "accept", with a line each in `migrating.md`.

## Phases

All are MMP work except the review in phase 5. Sizes as in
[`replacing-flopy-mf6.md`](../integration/replacing-flopy-mf6.md): small is days,
medium is weeks.

| Phase | Work | Size | Done when |
|---|---|---|---|
| 0. Measure | Move the audit into `benchmarks/`; trace the construction peak | small | The audit runs on demand, and the construction peak is explained |
| 1. Contract and streaming | The seam; streaming generators for arrays; chunked binary; flat arrays; chunks spanning layers; correct the docstrings; reserve `chunks=` | small to medium | Griddata peak doesn't grow with `nlay` for inline, open/close and binary |
| 2. Lazy writes everywhere | Period arrays; lazy `dense()`; NetCDF; checks in the write pass; streaming lists; the fast writer | medium | Every array form passes the compute and memory tests, and MF6's results match numpy's |
| 3. Lazy array load | `load(chunks=...)`; the deferred reader; #516 and #368; unchanged write-through; the hazards | medium | Writing an unchanged model reads no array values, and the hazard tests pass on all three OSes |
| 4. Lazy lists | Deferred per-period lists, binary first; user-built lazy lists | medium | The target model's list data fits the memory limit |
| 5. Scale | The target model; docs; review the defaults | medium | The target is created, written and reloaded under a memory limit |

Phases 0 to 2 are mostly writer-side and can start now, if streaming stays
byte-identical for lazy arrays while the equivalence harness comes up. Phases 3
and 4 change ingress, so they wait for `simplify-converter`
([`converter-rebase.md`](../io/converter-rebase.md)), which rewrites it. Check the
writer work against that branch too.

Export phase 2's `dense()` is built lazy to start with, so phase 2 here and export
phase 2 should be done together.

## Tests

1. **Compute budgets.** A counting or raising scheduler across operation, array
   form and chunk layout. Fast enough for every PR.
2. **Memory slope.** Vary `nlay` and assert that growth is flat, not an absolute
   limit, so it holds across machines. Use `pytest-memray` for NetCDF, where
   `tracemalloc` may miss the C allocations.
3. **Corpus with random chunks.** Tier E with every array wrapped in randomly
   chunked dask, comparing MF6's results. This finds implicit computes in every
   package at little cost, and it builds on the MMP harness.
4. **Actually larger than memory.** Nightly, an array about 3x a container's
   memory limit (`benchmark.yml`), using a cgroup limit rather than `ulimit -v`,
   which interferes with memory maps.
5. **Hazards.** Self-overwrite, a changed source file, and Windows file locks.

## Requirements

Added to [`srs.md`](../../srs.md): FUNC-18 to FUNC-20, NFR-8 to NFR-10, SYS-4, and
the target in FUNC-8.

## Out of scope

- **Running the target model.** MF6 loads everything into RAM, so it needs a
  large-memory or parallel machine. MF6 still runs at small scale in CI, for
  NFR-9.
- **Splitting models.** Models this size will often be split, and `model_splitter`
  is planned as legacy-only. That needs its own plan.
- **Reading output.** `heads_reader.py` is already lazy per time step.

## Open questions

- A default `binary_threshold`.
- Whether a lazy constant can ever be written `CONSTANT`.
- Whether `xarray-extras` holds up on maintenance and platforms. If not, we pin it
  or drop the option; we still don't write a kernel.

## Limits of the evidence

- Synchronous scheduler, small grids and no MF6 runs.
- The formatter benchmark is one synthetic array.
- The streaming prototype covers only the `internal` case.
- A first run on a 32 MB `k` was killed (exit 137). That may have been an
  interruption, and wasn't diagnosed.
- `npf.to_xarray()` failed on scalar griddata under a parent, which may be the
  `to-xarray-constants` bug.

## Reproducing

Run from the repo root with `pixi run -e dev python <script> <scratch dir>`. Each
script makes its files in a temp directory inside the one given.

| Script | Shows |
|---|---|
| `compute_audit.py` | chunks computed per operation, and the code computing them |
| `memory_sweep.py` | peak against `nlay` at a fixed chunk size; with `icelltype=0` instead of the lazy array, the 118 MB floor |
| `heap_snapshot.py` | what's held at the last chunk |
| `stream_prototype.py` | streaming vs. the current writer, including bytes |
| `format_bench.py` | formatters; give it a directory with `xarray-extras` installed (`uv pip install --no-deps --target <dir> xarray-extras`) instead of a scratch directory |
| `flopy3_lazy.py` | when flopy3 reads external files |
