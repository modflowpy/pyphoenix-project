# Elevations for RCHA/EVTA arrays

Follow-up to #490, which put z coordinates on arrays on the grid's
layers.

## Where things stand

Package arrays on all of the grid's layers get `z_top`/`z_bot`/`z`, the
elevations of their cells (`Package._with_cell_centers`, via
`vertical.z_coords`). DIS/DISV `top` has a size-1 `layer` dim and gets
layer 0's, since it's the top layer's cells' tops.

RCHA's `recharge`/`irch`/`aux` and EVTA's `surface`/`rate`/`depth`/`ievt`/
`aux` also come out with a size-1 `layer` dim, `(kper, layer=1, row, col)`
or `(kper, layer=1, cell)`, but get no z coordinates, except in a 1-layer
model, where the shapes happen to match `botm`. Their values don't belong
to a fixed layer:

- `irch`/`ievt` (period arrays, `shape=("ncpl",)`, `index=True`, fill
  forward) give the layer each vertical column's recharge/ET goes to.
  Without them it's layer 1 (0 here).
- Unless `fixed_cell` is set, recharge/ET in an inactive cell
  (`idomain < 1`) moves down to the highest active cell below it.

So the cell a value belongs to depends on the period, on `irch`/`ievt`,
on `fixed_cell` and on `idomain`. Layer 0's elevations would be wrong
wherever any of those move it.

## Plan

1. **Resolve the target layer**: a function, say
   `rch_layer(irch, idomain, fixed_cell) -> DataArray` on
   `(kper, row, col)`/`(kper, cell)`, giving each column's layer per period:
   - `irch`'s value (check whether it's stored 1- or 0-based: it's an
     `index=True` field), else 0;
   - without `fixed_cell`, the first layer at or below it with
     `idomain > 0`;
   - where there's none, -1, and NaN elevations.
   EVTA uses the same function with `ievt`.
2. **Take the elevations at that layer**: index `z_coords(top, botm)` by
   the layer along `layer` (as `vertical.sel_z` does with `layer_at`),
   giving `z_top`/`z_bot`/`z` on `(kper, row, col)`, plus the chosen
   `layer` as a coordinate, as `sel_z` keeps it.
3. **Attach them** in `_with_cell_centers` for RCHA/EVTA period arrays,
   dropping the size-1 `layer` dim's place in the coordinates' dims.
   Unlike other z coordinates these vary with `kper`; check that
   `sel_z`/`mask_z` handle the extra dim (they should broadcast).
4. **Changing `irch`/`ievt`**: the coordinates are computed when the array
   is built, so they're as fresh as `to_dataarray`. Note it in the
   docstring rather than caching.

## Open questions

- **Dry cells.** MF6 may also move recharge/ET below a cell that goes dry
  during the run. That isn't knowable from input, so the input
  coordinates describe where the input puts it. Check the MF6 source
  (`gwf-rch`, `bnd` `nodeu`/`reassign`) for exactly what moves and when.
- **EVTA `surface`** is itself an elevation, like `top`, but the ET
  surface, not a cell face. It gets the target cell's coordinates like the
  others; its own value is data.
- **List-based RCH/EVT** have cellids with a layer, so they have a fixed
  cell. Check whether their gridded form (`to_xarray(grid=True)`) gets z
  coordinates; it should, from the cellid's layer.
- **DISU**, as for the rest of the z work, waits on horizontal selection.

## Tests

- `irch` given, varying by column: the elevations are those of each
  column's `irch` layer.
- No `irch`: layer 0's, the same as `top`'s.
- An inactive target with and without `fixed_cell`: moved down vs. NaN.
- `irch` changing between periods: the coordinates differ by `kper`.
- DISV EVTA with `ievt`.
- `sel_z`/`mask_z` on a recharge array.
