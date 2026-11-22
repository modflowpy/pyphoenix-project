# Write options

Status: implemented locally (2026-10-10), not pushed; see "Implemented"
below. Drafted 2026-10-09 against develop `c3d9a88`. Covers what's left
on #256 ("Configurable write options").

## Implemented

Branches, each on the one before unless noted (in the
`write-context-cleanup` worktree):

| Branch | Commit | Step |
| --- | --- | --- |
| `fix-internal-factor` (from develop) | `ab5de11` | 1 |
| `fix-grid-array-rows` (from develop) | `11e3cf4` | found on the way, see below |
| `write-context-cleanup` | `833b028` | 3c, 3d |
| `array-write-context` | `8cf1c16` | 2 without `path`, IPRN |
| `external-arrays` | `dc73c79`, `52af602` | row fix cherry-picked, 3a + `ArrayIO.path` |
| `binary-arrays` | `da30ac0` | 3b + `ArrayIO.binary` |
| `array-file-followups` | `0f10932`, `40bcd12`, see below | hashes + strict, `ArrayIO.how`, one `ArrayFormat` |

Decisions made along the way, where the plan was open or turned out
wrong:

- *One vocabulary* (last commit, superseding the `use_binary`,
  `ArrayIO.binary` and `ArrayIO.how` items below): `ArrayFormat =
  "constant" | "internal" | "open/close" | "binary"`, the control record
  kind, for both `WriteContext.array_format` and `ArrayIO.format`.
  "constant" means CONSTANT where the values allow, else INTERNAL; unset,
  the writer chooses. `ArrayIO.layered` is the separate LAYERED axis.
  Loading records each record's kind as is. A context's `array_format`
  overrides lower contexts' formats, and if inline their paths; a path
  beats an inline `array_format` of its own context. `binary_threshold`
  qualifies "binary". `use_binary` is gone, `ArrayFileError` is
  `ExternalFileError`.

- *Row bug.* MF6 reads a structured grid's ASCII layer one READ per row,
  each from a new line, and develop wrote a layer per line, which MF6
  rejects. Fixed on its own branch (egress reshapes griddata like the
  grid). Found by the first MF6 run of OPEN/CLOSE files.
- *`array_format`* is `None | "internal" | "open/close"`; `"constant"` is
  gone. `"internal"` in a context drops lower contexts' paths and binary
  (loaded ones included); an `ArrayIO.path` in the same context still
  wins.
- *File names*: `<filename with . as _>_<field>[_p<kper>][_l<layer>].txt`
  (`.bin` for binary), 1-based, beside the component's file.
- *`Component.root`*: the paths' base is the nearest ancestor's
  workspace; a standalone component's is its absolute filename's
  directory, else the cwd.
- *Shared files*: within a component, as planned. Across components (one
  `sim.write()`, tracked by `write_session`), the first writer keeps the
  file and a later one that disagrees goes inline. The collision check
  covers files written in the session, not files already on disk.
- *Outside files*: copied in as planned. Arrays sharing one outside file
  share its copy.
- *Binary, per MF6's source*: MF6 reads the header and then as many
  values as the array holds, checking only the file size; the header's
  sizes are just logged. So a non-LAYERED binary array is one header for
  the whole array, a LAYERED one a file per layer. Our reader trusted
  the header's NROW*NCOL and would have read one layer of a full-grid
  file; it now reads every value after the header.
- *`use_binary=True`* alone implies files (`.bin` names), unless
  `array_format="internal"`; set in a context it overrides lower
  contexts' `ArrayIO.binary`. Loaded text files are recorded
  `binary=False`, so they stay text unless a higher context says
  otherwise. `binary_threshold` is per file written (a layer, for a file
  per layer), binary when *bigger* than it, as the old docstring said;
  it still does nothing without `use_binary`.
- *Hashes*: blake2b-128 of the values as written (`array_hash`), taken
  only for OPEN/CLOSE records, compared only when a shared file's arrays
  disagree. Not part of `ArrayIO` equality.
- *Strict*: `WriteContext.strict` raises `ArrayFileError` for both rules,
  before the component writes any file; `_write_mf6` now prepares
  arrays before opening (and truncating) the component's own file.
- *`ArrayIO.how`*: `"internal" | "layered"`. Loading records INTERNAL
  records and LAYERED arrays; CONSTANT needs nothing, the writer picks
  it for uniform values anyway. A form the values no longer allow is
  ignored. A layered field's non-LAYERED INTERNAL array is written as one
  record, which MF6 runs to the same heads.

## Where #256 stands

Done:

- `WriteContext` (#276): passed to `write(context=...)` or entered as a
  thread-local context manager.
- `float_precision`: lossless by default since #372, used by the
  CONSTANT/INTERNAL macros.
- `use_netcdf`: `array_how()` routes arrays egress marks `netcdf` (#286).
- Period mask: no longer needed. It was for finding the non-empty periods
  of dense `nper`-dimensioned arrays at write time. Period data is now
  sparse dicts keyed by period, so the keys are the mask: list packages in
  #336/#348 (OC in #360), A/G packages in #410/#415.
- G/A flavor choice: no longer applies. The flavors stay separate classes
  (`Wel`/`Welg`, `Rch`/`Rcha`, ...), so the user picks one by picking a class.

Left, below: (1) INTERNAL FACTOR is dropped on load, a bug; (2) array
options detected on load (IPRN, external files, binary) don't survive to
write, and can't be set per array; (3) four `WriteContext` options are
declared but nothing reads them.

## 1. Bug: INTERNAL FACTOR is ignored on load

`_read_control_record` (`converter/ingress/structure.py:210`) applies
FACTOR only for OPEN/CLOSE (`_read_open_close_values`). For INTERNAL it
reads the values and drops the FACTOR token, so this loads `k` as
`[1, 2, 3, 4]`, not `[10, 20, 30, 40]`:

```
k
  INTERNAL FACTOR 10.0
    1.0 2.0 3.0 4.0
k33
  OPEN/CLOSE k.txt FACTOR 10.0   # loads scaled, correctly
```

The model MF6 runs differs from the one flopy4 loads. Fix first, on its
own: parse the control record's options once (FACTOR, IPRN, (BINARY)) for
all three kinds, apply FACTOR for INTERNAL and OPEN/CLOSE. CONSTANT has
no FACTOR. Same path serves griddata and READARRAY period blocks, so one
fix covers both. Test both, plus LAYERED with a per-layer FACTOR.

The typed grammar (`typed.lark:26-32`) already parses these options, and
its transformer returns `{"factor": ...}`, but ingress doesn't use that
path. Don't revive it here.

## 2. Per-array write settings, filled in on load

By default, flopy4 should write a loaded component the way its file had
it: the same external files, binary where it was binary, the same IPRN.
"Load, change one thing, write" shouldn't move every array inline.

### Settings are write configuration, not model data

The old plan kept these in `DataArray.attrs`. That doesn't work now:
array fields hold plain `ndarray`s (`Npf.k` is an `ndarray`), and
DataArrays only exist in egress, built fresh each write. Other places
they could go, and why not:

- A side table of per-field state on each component: model state that
  isn't the model, and it needs invalidating when arrays change.
- An `ndarray` subclass carrying them: leaks into `type(npf.k)`, and
  which operations keep the metadata is unpredictable.
- A registry keyed by array identity: arrays aren't hashable, and
  reshapes or copies in converters break identity silently.
- Fields as DataArrays again: reverses the move away from them.

What makes it simpler: every setting is a hint the writer can apply to
whatever values the array holds *now*, and a stale one is never wrong.
An old path rewrites that file with the current values; an old BINARY
writes them as binary; an old IPRN prints at the old format. So nothing
needs invalidating: no `on_setattr` hooks, and in-place edits
(`npf.k[0] = 5`) are fine. Two exceptions, where a path hint can't just
be followed: files several arrays share, and files outside the
workspace. See "Paths the writer can't just follow" below.

Hints that are harmless when stale are configuration, so they go in
`WriteContext`:

```python
@attrs.frozen
class ArrayIO:
    iprn: int | None = None
    path: Path | None = None    # OPEN/CLOSE file, relative to the sim dir
    binary: bool | None = None

WriteContext(arrays={
    "k": ArrayIO(path="gwf/npf_k.bin", binary=True),
    ("recharge", 3): ArrayIO(path="rch/kper4.txt"),
})
```

Keys are relative to the component: a field, or (field, kper) and
(field, kper, layer) / (field, layer). Nothing is global, so renaming a
model doesn't break them. Keys that no longer match (`nlay` shrank) are
ignored.

Every `ArrayIO` field is optional, `None` meaning unset, like the
whole-write options (see Precedence). Entries for the same key at
different levels merge field by field, so a higher context's
`arrays["k"] = ArrayIO(iprn=1)` sets IPRN and keeps the loaded path and
binary.

### Attached per component

- `Component.write_context: WriteContext | None`, default `None`, not
  written to file and ignored by equality and `to_dict` (like `filename`).
- Loading sets it to a context whose `arrays` reproduce the file's
  layout. Ingress fills it in `_read_control_record`'s callers.
- A user sets the same thing by hand to make one array binary or
  external, or set its IPRN. That was the issue's original ask.
- Egress copies the matching `ArrayIO` onto the DataArray it builds, as
  `attrs`, which `array_how()` and the macros read.

### Precedence

Contexts rank, highest first:

1. the `write(context=...)` argument
2. `WriteContext.current()`, the innermost `with WriteContext(...)` block
3. the component's own `write_context` (loaded, or set by hand)
4. the nearest ancestor's `write_context`
5. the default

The context manager ranks above components: a `with` block is as
deliberate as an argument. So the rule is that anything said for this
write beats what the file had.

A setting from a higher context beats any from a lower one. Within one
context, a per-array setting beats a whole-write one, and `use_netcdf`
beats `array_format` (3a). Across contexts, only rank matters. So:

- `sim.write(context=WriteContext(array_format="internal"))` inlines
  every array, loaded layouts included.
- `WriteContext(array_format="internal", arrays={"k": ArrayIO(path=...,
  binary=True)})` inlines everything except `k`.
- `sim.write(context=WriteContext(float_precision=4))` keeps every
  loaded layout: that context says nothing about formats.

That last case needs "unset" distinct from the default. `array_format`
already has it (`None` means automatic). `use_binary` and `use_netcdf`
become `bool | None`, default `None`: `None` defers to lower contexts,
then to the built-in default (`False`); an explicit `False` overrides.
`binary_threshold` is `None`-able already.

`float_precision=None` means "lossless" today, not "unset", so lossless
gets its own value: `float_precision: int | Literal["lossless"] | None`,
default `None`, resolving to `"lossless"` when no context sets it. The
writer filters (`format_float`, `array2const`, `array2string`) and
`to_numpy_printoptions()` keep taking `None` for lossless internally, or
switch to `"lossless"` too; the resolved context never hands them an
unset value either way. One caller depends on the old meaning:
`ncf_methods.py:23` forces lossless with `float_precision=None`, which
under the new rule would defer to lower contexts instead. Change it to
`"lossless"`. `test_ncf_subpackage_float_precision`
(`test/mf6/test_mf6_component.py:1378`) covers it.

The NCF override needs more than the rename. It does
`attrs.evolve(context or WriteContext.current(), ...)`, which picks one
context and skips the chain, then passes the result to `super().write()`
as the argument, which now ranks highest. Instead, resolve NCF's chain
like any component's and apply lossless on top of the resolved context.

To discard a component's layout permanently, set
`npf.write_context = None`.

`Component.write` passes its `context` argument (not `active_context`)
to children (`component.py:577`). Resolve per component instead: each
child resolves its own chain, since it has its own `write_context`.

IPRN follows the same rule, so a `with` block that sets IPRN overrides
the loaded IPRN of every array under it. Consistent, and probably fine,
but users who care about IPRN are the ones who'd hit it.

### Paths the writer can't just follow

A path hint is safe when stale only if the file belongs to one array and
sits inside the workspace. Two cases break that.

**Shared files.** Several arrays can name one file: RCHA periods 1 and 5
both `OPEN/CLOSE rch.txt`, or two packages sharing a file. Edit one and
the writer would write `rch.txt` twice with different values, the second
silently overwriting the first.

The conflict can only be caught at write time. In-place edits
(`rch.recharge[0][:] = 0.001`) don't notify anything, so a check at
modification time would catch reassignment and miss these. At write
time, it shows directly: the arrays sharing a file don't agree.

Nor can the writer know what the user meant: period 1 only, or the file,
i.e. every period using it. So it doesn't guess quietly:

- Egress groups arrays by resolved path.
- A group whose arrays agree: write the file once, keep the layout.
- A group whose arrays disagree: write every array in it internal, and
  warn, naming the file and the fields/periods that used it. The whole
  group, since nothing says which array is the edited one; keeping the
  file for any of them is a guess. The result is exactly the model in
  memory, and the warning says how to restore a layout with `ArrayIO`.

Follow-ups:

- *Load-time hashes.* Hash each loaded array (blake2b, about 32 bytes;
  load reads every value anyway) into `ArrayIO.hash`. At write time that
  says which arrays changed since load, not only that a group disagrees:
  unchanged ones keep the file, changed ones go internal, and the warning
  names them ("rch period 1 changed and was written internal; periods
  2-4 still use rch.txt"). Hashing doesn't speed up the group check by
  itself, since it reads every value just as comparing does; what it adds
  is knowing what changed. A false "changed" (collision, `-0.0` vs `0.0`,
  NaN payloads) only costs layout. No hash (a user-made `ArrayIO`, or a
  dask array not hashed at load) falls back to the group rule.
- *Strict mode.* An option to raise instead of warning.

**Files outside the workspace.** A path like `../data/k.txt`, or an
absolute one, would have the writer write outside the workspace: writing
a loaded simulation to a fresh directory would overwrite the original
input data, with nothing edited. Never write outside the workspace.
Copy the file in instead:

- Keep the basename: `../data/k.txt` becomes `k.txt`.
- Put it beside the referencing component's file (`gwf/k.txt` for a
  model in `gwf/`).
- On a collision, two outside files with one basename (`../a/k.txt`,
  `../b/k.txt`) or a file of that name already in the workspace, add a
  suffix (`k_1.txt`).
- Warn with the old and new path.

Both rules apply to `ArrayIO.path` set by hand too, not only loaded ones.

### FACTOR isn't kept

FACTOR is applied on load (1) and not written back. Keeping it is the
one hint that changes the numbers written, not where or how:

- Keeping raw values plus the factor makes `npf.k` hold values MF6
  doesn't run, and losing the factor (say `write_context = None`) writes
  a wrong model. It stops being a safe hint.
- Writing `values / f` with `FACTOR f` is exact for MF6 but not as text:
  for `v = 1..1000`, `f = 0.1`, 149 values come back like
  `3.0000000000000004`. Fixing that means a shortest-decimal search over
  every value on every write.
- Keeping the raw values too, to write them verbatim when unchanged,
  doubles memory for every factored array and forces dask arrays into
  memory for the comparison.

The scaled values with no FACTOR are the same model, so drop it.

Depends on 3a for `path`: no external writer exists yet. IPRN can land
first.

## 3. `WriteContext` options nothing reads

### 3a. External (OPEN/CLOSE) arrays — `array_format`

There is no external writer. `macros.jinja` has an `"external"` branch,
but `array_how()` never returns it, and the branch would print the array
after OPEN/CLOSE, not a filename.

- Add `"external"` and `"layered external"` to `array_how()`, chosen by
  `array_format="open/close"`, or by an `ArrayIO.path` (2).
- Write the values to a file beside the component's file. Name:
  `<component filename stem>.<field>[.<layer>|.<kper>].txt`, unless
  `ArrayIO.path` gives one.
- Writing a second file per array means the template can't do it: the
  macro only renders the control record. Write the files in egress, or in
  `_write_mf6` right after `unstructure`, and pass the paths through.
- `array_format="internal"` / `"constant"` forces that format: "constant"
  is an error for an array that isn't, so it really means "allow
  constant". Consider dropping `"constant"` and keeping
  `None | "internal" | "open/close"`.
- Netcdf stays a separate switch: `use_netcdf` wins over `array_format`.

### 3b. Binary arrays — `use_binary`, `binary_threshold`

Builds on 3a. Write `OPEN/CLOSE <file> (BINARY)` with the 52-byte header
`_BINARY_ARRAY_HEADER` (`converter/ingress/structure.py:96`) the reader
already decodes: one record per layer, float64 or int32 data.

- `use_binary=True`: external arrays are binary. On its own, implies
  external.
- `binary_threshold`: binary only for arrays at least this many bytes.
  Others follow `array_format`. Without `use_binary` it does nothing;
  either error or fold the two into `binary_threshold: int | None` with
  0 meaning "always".
- Check first how MF6 reads a binary array spanning every layer and not
  LAYERED: one record per layer, or one record for the whole grid. "One
  record per layer" above comes from our reader (one header, `nrow *
  ncol` values per record), not from MF6's source.
- Test against MF6 itself, not only our reader: no corpus model uses
  binary input (0/242), so our reader has only been checked against
  itself and flopy3's tests.

### 3c. `use_relative_paths`

Nothing reads it. Paths are always written relative to the simulation
directory (`Component.filename`, POSIX since #376). Relative is what MF6
wants and what makes a workspace movable.

Recommendation: drop it. If kept, `False` would write
`workspace.absolute() / filename` in namefile rows and file records
(FILEIN/FILEOUT, OPEN/CLOSE from 3a), a few places in egress.

### 3d. `get_float_format()`

No callers; `array2string`/`array2const`/`format_float` take the
precision directly. Remove it.

## Not covered

- *Array form.* (Since covered by `ArrayIO.how`, step 6.) A loaded
  INTERNAL array whose values are all equal is written CONSTANT, and a
  non-layered one whose layers are each uniform is written LAYERED. MF6
  reads them the same, but a round-trip diff shows it.
- *NETCDF input.* Ingress doesn't load NETCDF arrays, so there's nothing
  to record. NETCDF stays a whole-write switch (`use_netcdf`) until it
  does.
- *FACTOR*, by design; see above.

## Order

1. 1 (bug fix, standalone PR).
2. 3c, 3d (drop dead options; small).
3. 2 without `path`: `Component.write_context`, precedence, the
   `None`-means-unset types (`use_binary`/`use_netcdf` as `bool | None`,
   `float_precision="lossless"`, all-optional `ArrayIO`), the NCF
   override, IPRN.
4. 3a, then `ArrayIO.path`, with the shared-file and outside-workspace
   rules.
5. 3b, with `ArrayIO.binary`, after checking MF6's binary layout.
6. Follow-ups: load-time hashes, strict mode, `ArrayIO.how`.

All six done, on local branches (see "Implemented").

Once 1 ships, split 2 and 3 into their own issue and close #256 with
pointers to it, and to #336/#348/#360/#410/#415 for the period mask.
