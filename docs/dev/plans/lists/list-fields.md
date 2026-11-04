# List fields

How DFN `list` fields (packagedata, connectiondata, period blocks and other
tabular input) are represented. A reference note, to become a developer doc
(see [`dev-docs.md`](../maintenance/dev-docs.md)).

## Representation

A list field is a list of typed rows. Each row is an `Item` (`item.py`), an
attrs class generated from the DFN's record, nested in the package class.
A union (keystring) list has one arm class per keyword.

```python
class Chd(Package):
    @attrs.define
    class StressPeriodData(Item):
        cellid: tuple[int, ...] = cellid_()
        head: Union[float, TimeSeriesRef] = double(time_series=True)
        aux: tuple[Union[float, TimeSeriesRef], ...] = array(
            default=(), shape=("auxiliary",), time_series=True, optional=True
        )
        boundname: Optional[str] = string(
            default=None, empty_is_none=True, optional=True, when="boundnames"
        )

    _stress_period_data: Optional[dict[int, list[StressPeriodData]]] = list_(
        alias="stress_period_data", block="period", fill_forward=True, ...
    )
```

| Category | Example | Python type | Item type |
|---|---|---|---|
| Static list block | LAK packagedata | `Optional[list[Item]]` | record |
| Repeating block, tabular | CHD period | `Optional[dict[int, list[Item]]]` | record |
| Repeating block, keystring | OC period | `Optional[dict[int, list[Item]]]` | union of arm classes |
| Repeating block, flag | STO period | `Optional[dict[int, str]]` | `str` |

Repeating blocks are keyed by the 0-based period. A period not given
inherits the last one given (fill-forward).

**Storage.** Since #479, a tabular list's rows can be held as columns in an
`ItemTable` (`item_table.py`), a numpy array per field like flopy3's
recarrays. It's still a list of Items: each row is a view onto the columns.
A list block loads by the fastest reader its rows allow, each falling back
to the next: `read_rows` (numbers only, by column with numpy),
`Item.from_rows` (a layout planned once per row length), `Item.from_tokens`
(a row at a time).

**Dimensions** that count rows (`nlakes`, `maxbound`, `nper`) follow the
lists. A dimension is either computed live (CHD's `maxbound` property) or a
field kept in step by `Package._sync_dims` wherever dims are read or
written. An exact dimension takes the row count; a bounded one
(`"<=maxats"`) is the user's, and is only checked. Assigning a dimension
that disagrees with its list raises. An in-place append isn't seen until
the next sync (see the [backlog](../maintenance/backlog.md)).

**Input.** `Package._coerce_item_list` accepts Items, tuples or lists
(positional, `Item.from_values`), dicts (named columns) and a dict of lists
(columns). Union rows are dispatched to their arm by keyword token, or by a
`"keyword"` key in a dict. A row with a field an option turns on (a
boundname) sets that option.

**Views.** `Package.to_dataframe()`/`from_dataframe()` give and take stress
period data as a tidy DataFrame. `to_xarray` gives period lists as a dense
or sparse dataset (#476; see
[`representation.md`](../xarray/representation.md)).

## Row layout

A row's layout is fixed by the component's dimensions, except for its last
field (the DFN spec's rule for inline arrays). An inline array sized only by
dims may be anywhere; one whose width varies by row (self-sizing, sized by a
sibling, or by a lookup) must be last.

Reading a file row and building an item from a Python tuple are the same
problem, splitting a sequence of values into fields; only the per-field
conversion differs (file tokens are strings and 1-based, Python values typed
and 0-based). So there's one layout, shared by both, and no value sniffing:
as in MF6, every width comes from package context. The exception is a
union's arm, which its own tokens choose: a keyword arm by its keyword;
OBS's `id` (cellid, index or string, followed by `id2`) by whether its first
token is a number.

Given a row's values and the package context, fields are walked in order:

1. **Each field takes its width.** A scalar 1, a cellid its grid's
   `ncelldim`, a dim-sized array its dims' value (aux by `auxiliary`, GNC
   `cellidsj` by `numalphaj`, EVT `pxdp` by `nseg-1`).
2. **Flat or tupled** (Python input only). If the next value is a sequence
   (not a str) or `None`, it's the whole field (`None` is an unset optional
   field, or an `allow_zero` cellid referring to no cell). Otherwise the
   field takes its width in scalars, so `((0, 2, 3), 1.0)` and
   `(0, 2, 3, 1.0)` are both a CHD row.
3. **The last field**, if its width varies by row, takes the rest, minus a
   boundname if there is one.
4. **A boundname is present iff `boundnames` is set** (the field's
   `when`). Reading a file this is strict. For Python input, a row with
   exactly one value more than the layout allows has a boundname, and the
   package sets the option. Any other surplus is an error. It's decided by
   count, never by the value's type.
5. **An optional untagged group** (EVT's `petm0`) is present iff its gating
   option is set (`SURF_RATE_SPECIFIED`) where that's recorded; otherwise
   by the value count.

The context is a `RowContext` (`item.py`): `ncelldim` per grid, dim sizes,
and the enabled options. A package built standalone, before it's in a
model, doesn't know `ncelldim`; the width is then inferred from the value
count when it's the only unknown, and an ambiguous row raises, asking for
the cellid as a tuple or for the package to be attached first. Without a
package there's no context, and an item takes one value per field.
Widths, including lookup-sized arrays (`len(ic) == packagedata.ncon(ifno)`),
are checked by the package after construction.

## Why rows, not columns

The earlier design exploded each list field into one `NDArray` attr per
column, with buffer attrs, scatter/gather in `__attrs_post_init__`, a
`__block_col_maps__` schema, fill values for absent cells, and converter
special cases (`structure_array`, `_hack_period_non_numeric`) to reassemble
rows on write. That mixed up storage and view: the DFN describes rows, the
object model should too, and columns are a view. `ItemTable` brings back
columnar storage for speed, behind the row interface.

Rows rather than a DataFrame as the primary form:

1. Unions (keystrings) don't fit a DataFrame without collapsing types into
   `None`/`NaN` columns.
2. `list.append`, `item.field = value` and comprehensions are idiomatic for
   editing a few rows; `pd.concat` and `.loc` aren't.
3. A typed list is statically checkable; a DataFrame isn't.
4. One pattern in codegen and the converter for every item type.

DataFrames are a view and an accepted input.
