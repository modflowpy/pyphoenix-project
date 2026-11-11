# Fixing the silent loss of period data on trailing text

`Simulation.load` silently drops every period block of a file whose blocks end `END PERIOD 1`,
if text follows the last one. This is a one-line fix to a regex. Tested at `8d25e4b7`, in a
throwaway worktree. Nothing here has been applied.

Found by the DDL slice's corpus run, 2026-11-05.

## What to do

1. **Apply the regex and the test below, as one small PR.** It's silent data loss with a one-line
   fix, and on the corpus it changes only `test021_twri`. CI runs the full suite.
2. **Add a warning when the trim removes text,** naming the file and the lines. I'd do this in the
   same PR or straight after. It's what would have made this bug visible, and it isn't tested yet.
3. **Leave text between blocks for later.** With the fix it raises where it used to lose data
   silently, which is already better. Accepting it, as MF6 does, is a separate decision (see
   "Related").
4. **Afterwards, rerun `test021_twri` through the DDL slice,** since its recharge is missing from
   the slice's results.

Don't widen this into the OC load bug (`oc-format-load-bug.md`), which is unrelated.

## The problem

`mf6/test/test021_twri` loads without an error, with `recharge=None` on its RCHA. MF6 applies
that recharge: the nightly `db59037` runs the model, with 13,608,000 of `RCHA` inflow in the
budget. `twri.rch` has MODFLOW-2005 lines left after its last block:

```
BEGIN PERIOD 1
  RECHARGE
    CONSTANT 3.E-8
END PERIOD 1

         1         0    NRCHOP,IRCHBD
```

When a file fails to parse, `loads_typed` and `_parse_basic` cut it back to the last block
`_BLOCK_RE` recognizes (`flopy4/mf6/codec/reader/__init__.py:21`), and parse again. That
regex allows one word after `END`. So `END PERIOD 1` doesn't end a block, the last match is
`END OPTIONS`, the trim removes every period block, and the second parse succeeds. A bare
`END PERIOD` is fine, which makes this look intermittent.

It isn't specific to RCHA. A WEL file loses its 40 rows the same way.

## The fix

Allow anything after `END`, as MF6 does:

```diff
-    r"^[ \t]*begin\s+\S+.*?^[ \t]*end\s+\S+[ \t]*$",
+    r"^[ \t]*begin\s+\S+.*?^[ \t]*end(?:[ \t][^\n]*)?$",
```

The comment above `_BLOCK_RE` can stay as it is.

## Test

`test/mf6/test_mf6_reader.py`:

```diff
--- a/test/mf6/test_mf6_reader.py
+++ b/test/mf6/test_mf6_reader.py
@@ -1074,3 +1074,22 @@ def test_transform_record_header():
     keys = ["continuous FILEOUT Heads.csv", "continuous FILEOUT flows.bsv BINARY"]
     assert list(loads_typed(text, "utl-obs")) == keys
     assert [k.lower() for k in loads(text)] == [k.lower() for k in keys]
+
+
+TRAILING = "\n         1         0    NRCHOP,IRCHBD\n         1              INRECH\n"
+
+
+@pytest.mark.parametrize("end", ["END PERIOD", "END PERIOD 1", "end  period  1", "END PERIOD 1  "])
+def test_text_after_the_last_block_keeps_the_blocks(end):
+    """mf5to6 can leave MODFLOW-2005 lines after the last block, which MF6 ignores.
+    Trimming them mustn't take a block whose END has a period number with them."""
+    from flopy4.mf6.codec.reader import loads_typed
+
+    text = (
+        "BEGIN OPTIONS\nEND OPTIONS\n"
+        "BEGIN DIMENSIONS\n  MAXBOUND 1\nEND DIMENSIONS\n"
+        f"BEGIN PERIOD 1\n  1 1 1 -1.0\n{end}\n"
+    )
+    clean = loads_typed(text, "gwf-wel")
+    assert "period 1" in clean
+    assert list(loads_typed(text + TRAILING, "gwf-wel")) == list(clean)
```

It fails without the fix for the three `END`s with a number, and passes for the bare one.

`test_mf6_load_all_models.py` can't catch this, since the model loads. Comparing `twri`'s
recharge there would pin it on a real file, if that's worth a special case.

## How it was tested

| Check | Result |
|---|---|
| `test/mf6/test_mf6_reader.py`, with the fix | 49 passed |
| The new test, without the fix | 3 failed, 1 passed |
| What each package loads, before and after, on 253 corpus models (all but the Biscayne 8) | Only `test021_twri` changes, gaining `recharge` |
| A scan of the corpus's 36 input files with text after their last `END` (under 3 MB, without Biscayne) | Only `twri.rch` loses a block to today's trim |

The full test suite wasn't run, and is left to CI.

## Related, and not fixed by this

**Text between blocks.** MF6 skips it, and runs a copy of `test120_mv_dis-lgr` with
`some stray words here` before `BEGIN period 1`. Today flopy4 silently loses the period data
there too, by the same route. With this fix it raises `UnexpectedToken`. Stricter than MF6,
but no longer silent.

To accept what MF6 accepts, the trim could keep all the blocks, not just everything up to the
last one:

```python
def _strip_text_outside_blocks(data: str) -> str:
    matches = list(_BLOCK_RE.finditer(data))
    return "\n".join(m.group(0) for m in matches) + "\n" if matches else data
```

I tried this on that one copy only. It loads the recharge, and a bad array in the period still
raises. Line numbers in a later parse error would shift, and it hasn't seen the test suite. I'd
take the one-line fix first.

**The retry is silent by design.** A trim that removes text says nothing to the user, even
when it's right. A warning naming the file and the lines dropped would have made this bug
visible long ago, and it would help with mf5to6's leftovers generally.

**Real parse errors aren't swallowed.** A bad row in a period block, or a bad option, behaves
the same in both `END` styles: a bad row raises and an unknown option loads. Checked on WEL,
RCHA and MAW. The errors raised are `ValueError`s rather than Lark's, so these don't look like
they reach the retry, though I didn't trace it.
