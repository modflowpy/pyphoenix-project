# Merging `Item` into `Record`

One codec for row and line records. Follow-up to
[`field-functions-plan.md`](../archive/field-functions-plan.md). The
earlier steps of this plan are done (#463): list shapes stored under
`"shape"`, line records declared with the field functions, arrays found by
metadata (`spec.is_array`) and held as tuples. So are the
prerequisites: the cellid change (#466), the positional row layout (#467,
described in [`list-fields.md`](list-fields.md)), boundnames on `when`
(#478), and lookup-width validation.

## Terminology

Both are records in DFN terms:

- **Row records:** `Item` subclasses (`item.py`), one per list-block row.
- **Line records:** plain `Record` subclasses (`record.py`), one per
  keyword line in a non-list block (NPF `XT3D [RHS]`, OC `Format`, TS
  `NAMES`).

The split is historical, not semantic.

## What the merged codec carries

`class Item(Record)` overrides `to_tokens`/`from_tokens` with:

- count-sized arrays (`_counted_fields`, post-init count fill);
- 1-based index and cellid, including signed;
- union columns (`_read_unions`);
- time-series values;
- the trailing boundname;
- contextual widths (`RowContext`) and `_columns` order.

All of it is driven by field metadata, so it's valid for any record.
`Record` has the plain forms `convert` accepts, nested records and tagged
values. The merged codec has both, and `Item` becomes an alias or goes
away.

Since #479, rows can also be stored as columns (`ItemTable`), so the merge
covers that path too: `read_rows` and `Item.from_rows` build rows from
columns and planned layouts, not through `from_tokens`.

## API

- `Item.from_values(values, context)` and `from_tokens` both call the
  shared layout. After the merge they're `Record` classmethods.
- Union dispatch (`construct_union_item`, `dispatch_union_item`) stays a
  free function, since it picks the arm class from the row's keyword, then
  calls the arm's classmethod.

Large; its own branch, with full CI.
