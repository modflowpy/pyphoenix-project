# Binary list input: which blocks MF6 can read

Which list blocks MF6 can read from a binary OPEN/CLOSE file, and what
flopy4's external list writing (`list_format`, `ListIO`, #520) does about
it.

## The constraint

MF6 reads an `OPEN/CLOSE <file> (BINARY)` list only into a block whose row
count it knows before reading.

- IDM (`src/Utilities/Idm/mf6blockfile/LoadMf6File.f90`) sizes a list
  block's `StructArray` from the recarray's DFN `shape`, when that names a
  DIMENSIONS variable (or a PACKAGEDATA per-row field, or `SUM(...)` of
  one).
- With no shape, the array is built with a *deferred* shape: it grows as
  text rows are read.
- `StructArray::read_from_binary` (`StructArray.f90`) refuses a deferred
  array outright:

  ```
  IDM unimplemented. StructArray::read_from_binary deferred shape not
  supported for binary inputs.
  ```

- Period blocks are fine: `Mf6FileList` sizes them by MAXBOUND.
- Otherwise the reader reads until EOF or `nrow` rows, with no header:
  each row's columns back to back, ints 4 bytes, reals 8.

## TDIS PERIODDATA

- In `doc/mf6io/mf6ivar/dfn/sim-tdis.dfn`, the recarray
  (`type recarray perlen nstp tsmult`) has no `shape` line. The generated
  `src/Idm/sim-tdisidm.f90` carries `''` for its shape, so the block is
  deferred and binary fails. This was seen running a simulation written
  with `list_format="binary"`.
- flopy4's generated `flopy4/mf6/tdis.py` nonetheless has
  `shape=("nper",)`. That comes from flopy4's codegen or the devtools
  schema, not from MF6's DFN (source not yet found).
- The mismatch runs the other way too. MF6 sizes LAK CONNECTIONDATA by
  `sum(nlakeconn)`, but flopy4's `Lak.connectiondata` has no shape.

So flopy4's `shape` metadata isn't, today, a reliable test for "MF6 can
read this list from binary".

## What flopy4 does now

- `list_format="binary"` writes **period** lists binary.
- Every other list goes to a text OPEN/CLOSE file under that setting,
  silently.
- A list whose own `ListIO` says `"binary"`, including one loaded from a
  binary file, is written binary wherever the row layout allows: the
  caller is claiming MF6 can read it.
- Rows MF6 can't read from binary at all fall back to text, with a
  warning if the list's own `ListIO` asked for binary. These are:
  - text columns (boundnames)
  - keywords and unions (OC, MAW/SFR/LAK period settings)
  - ragged arrays (DISV CELL2D's `icvert`)
  - time series names in numeric columns

## To lift the restriction

1. **MF6.** Add `shape (nper)` to the PERIODDATA recarray in
   `sim-tdis.dfn` and regenerate the IDM definitions. NPER is in TDIS's
   DIMENSIONS block, so `LoadMf6File` would resolve it and the array
   wouldn't be deferred.
2. **flopy4.** Make list fields' `shape` metadata come faithfully from
   MF6's DFNs: no added `nper` on TDIS, and add `sum(nlakeconn)` on LAK
   CONNECTIONDATA. Then widen the `list_format="binary"` rule in
   `external._list_target` from "period blocks" to "period blocks, or
   lists whose DFN declares a shape".
   - Gate this on the MF6 version (the contract), since older executables
     would still reject TDIS binary.
   - Newly eligible: DISV VERTICES, LAK PACKAGEDATA/OUTLETS, GNC data,
     exchange data (`nexg`), and TDIS once fixed. Some may still fall back
     on row layout (CELL2D).
