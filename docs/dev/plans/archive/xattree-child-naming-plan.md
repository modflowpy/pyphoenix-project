# xattree child-naming consolidation plan

**Status: superseded.** This plan scoped the child-naming consolidation
as **upstream** work in the `xattree` repo itself (owned by wpbonelli),
with flopy4-side cleanup (deleting `Component.pname`) gated on that fix
landing and being pulled in via a pin bump. That never happened —
`xattree` was dropped entirely instead ([`xattree-removal-plan.md`](xattree-removal-plan.md),
merged `develop`@`67d0922`, 2026-09-16), and the equivalent
one-rule-for-all-three-kinds naming logic this plan designed was built
directly in `flopy4/mf6/component.py`:

- `_resolve_child_name()` — the actual name-resolution/collision-check
  logic this plan's "Steps" section 2 called for (one rule for `only`/
  `list`-kind children; `dict`-kind resolves by mapping key, handled by
  the caller).
- `_attach_to_parent_field()` / `_set_child_parents()` — the two
  attachment paths this plan's "Current state" section identified as
  divergent in xattree (`_yield_children`/`_init_tree` vs. `_bind_tree`),
  now unified as bottom-up vs. top-down construction through one shared
  implementation instead of two disagreeing ones.

`Component.pname` — the workaround this plan's background section
describes — is deleted; `.name` itself now round-trips correctly for
all three child kinds, closing the gap this plan was written to close,
just via a different mechanism than originally scoped.

The design reasoning below (the three-kind naming problem, the
dict-kind silent-collision bug this plan found in xattree) is kept for
context in case the *specific* collision semantics ever need
re-deriving, but nothing here describes current behavior — read
`component.py`'s own docstrings for that.

## Original goal (for context)

One consistent rule for all three child kinds: a caller-given name
persists as the real attachment key (and therefore `.name`), with an
explicit-name collision raising immediately rather than silently
overwriting (the dict-kind bug this plan found in xattree: two children
given the same name on the same parent, from different fields, could
silently stomp one another because `xattree`'s `tree.children` was one
flat mapping filtered by type after the fact, not scoped per field).
Unnamed default behavior was to stay unchanged (field name for `only`,
`f"{field}{i}"` for `list`) so the change would be strictly additive for
existing code that never passes `name=` explicitly.
