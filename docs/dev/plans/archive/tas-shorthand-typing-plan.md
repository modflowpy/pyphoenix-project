# Type the time-array series name shorthand

Status: proposed (2026-10-06); not started. Small. Rechecked 2026-10-07
against develop `a6c52c8`, where the TAS period references landed (#413).
The `period_arrays` module docstring still shows `{0: "rchseries"}` with no
mypy caveat.

## Problem

Period arrays from a time-array series are typed
`dict[int, FloatArrayLike | TimeArraySeriesRef]`. At runtime a plain name
also works, `recharge={0: "rchseries"}`, because
`Package._init_period_arrays` converts it. mypy rejects it, because the
conversion happens in `__attrs_post_init__` rather than a field
converter. So [`mypy-converter-plan.md`](mypy-converter-plan.md)'s plugin won't cover it either:
there's no `converter=` for it to read.

The reference class is the typed form, and user code that checks
`isinstance(v, TimeArraySeriesRef)` already passes mypy. This plan is about
the shorthand alone.

## Options

1. **Document it, no code.** Say in the `TimeArraySeriesRef` and
   period-array docs that the typed form is `TimeArraySeriesRef("name")`,
   and that a plain name works at runtime but not under mypy.
   - Recommended.
2. **Widen the annotation** to `... | TimeArraySeriesRef | str`. The
   shorthand then type-checks, but reading a period types it as possibly
   `str`, which it never is after init. Every reader would have to
   narrow it away. Rejected for the same reason as widening the record
   flags.
3. **Move the conversion into a field converter**, so the mypy plugin
   could read it.
   - That needs `_init_period_arrays`'s work per field: dense input
     splitting, flattening, the int cast, and the time-series check.
   - The aux checks need `self` (the auxiliary names, the grid
     package's periods), which is why it's in post-init today (see
     [`period-storage-plan.md`](period-storage-plan.md)).
   - A converter with `takes_self=True` could do the per-field part.
     The cross-field checks would stay in post-init.
   - Worth it only if the plugin lands and more period-array input forms
     need typing, not for this shorthand alone.

## Steps (option 1)

1. In `TimeArraySeriesRef`'s docstring, state that a plain name is
   accepted at init but isn't the typed form.
2. Make the same note in `period_arrays`' module docstring, where the
   shorthand is shown.
3. Show the typed form first in any user docs or examples that use time
   series.
4. Revisit option 3 if [`mypy-converter-plan.md`](mypy-converter-plan.md) is done.
