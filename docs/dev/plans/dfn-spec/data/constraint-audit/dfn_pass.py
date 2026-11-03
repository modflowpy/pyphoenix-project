"""Constraint-bearing keys in the dev3 DFN snapshots (see docs/dev/plans/dfn-spec/constraint-audit.md).

Usage: python dfn_pass.py <snapshot dir> <options-labelled.csv> <out dir>
Writes dfn-constraints.csv (one row per constraint-bearing key) and prints tallies.
"""

import collections
import csv
import glob
import os
import sys
import tomllib

snap, labels_csv, out = sys.argv[1:4]
LABEL = {r["name"]: (r["category"], r["tags"]) for r in csv.DictReader(open(labels_csv))}

GRID_DIMS = {"nodes", "ncpl", "nlay", "nrow", "ncol", "nja", "nvert", "ncvert", "ncelldim",
             "nodesuser", "ncell2d", "ncell1d"}

rows = []


def add(comp, block, path, key, value, kind, level, cfgdata, trigger="", note=""):
    rows.append(dict(component=comp, block=block, path=".".join(path), key=key,
                     value=str(value), kind=kind, level=level, cfgdata=cfgdata,
                     trigger=trigger, note=note))


def cfgdata_of(block):
    return "config" if block in ("options", "dimensions") else "data"


def shape_kind(dims, comp_dims):
    """Classify a shape: grid-sized, bounded row count, schema-derived, or other."""
    kinds = set()
    for d in dims:
        d = str(d)
        if d.startswith("<="):
            kinds.add("bound")  # row count bounded by a dimension (config vs data)
        elif d in ("auxiliary", "naux"):
            kinds.add("schema")  # columns follow an option list
        elif d in GRID_DIMS or comp_dims.get(d, {}).get("scope") == "model":
            kinds.add("grid")
        else:
            kinds.add("local")
    return "+".join(sorted(kinds))


def walk(comp, block, path, f, comp_dims, in_record=False):
    cd = cfgdata_of(block)
    is_option = block == "options" and len(path) == 2
    opt = LABEL.get(path[-1]) if is_option else None
    t = f.get("type")

    if "valid" in f:
        lvl = "output" if (opt and opt[0] == "output") or comp.endswith("-oc") else "logical"
        add(comp, block, path, "valid", f["valid"], "K2", lvl, cd, note="enum domain")
    if t in ("integer", "double", "string", "keyword") or "dtype" in f:
        pass  # type itself: counted in tally only (every field has one)
    if "allow_zero" in f:
        add(comp, block, path, "allow_zero", f["allow_zero"], "K2", "layout", cd,
            note="0 is a null placeholder in a cellid list")
    if "index" in f:
        note = "1-based index" if f["index"] is True else "signed index: sign encodes a second attribute"
        add(comp, block, path, "index", f["index"], "K1", "layout", cd, note=note)
    for k in ("tagged", "case_sensitive", "layered", "netcdf", "mode_keyword"):
        if k in f and f[k]:
            add(comp, block, path, k, f[k], "K1", "layout", cd)
    if "shape" in f:
        sk = shape_kind(f["shape"], comp_dims)
        trig = "option:auxiliary" if "schema" in sk else ""
        add(comp, block, path, "shape", f["shape"], "K3", "logical", cd + ("" if "grid" not in sk else "<-config"),
            trigger=trig, note=sk)
    if not f.get("optional") and not in_record and t not in ("record", "union") \
            and not f.get("removed") and not f.get("deprecated"):
        add(comp, block, path, "required", True, "K4", "logical", cd, trigger="unconditional")
    if "when" in f:
        w = f["when"]
        lab = LABEL.get(w, ("?", ""))
        add(comp, block, path, "when", w, "K4", "logical" if lab[0] == "logical" else lab[0], cd,
            trigger=f"option:{w}[{lab[0]}{'/' + lab[1] if lab[1] else ''}]")
    if "default" in f:
        add(comp, block, path, "default", f["default"], "fill", "logical", cd,
            note="absence semantics, not a constraint")
    if "pk" in f:
        add(comp, block, path, "pk", f["pk"], "K6", "logical", cd)
    if "fk" in f:
        fk = f["fk"]
        tgt = fk if isinstance(fk, str) else fk.get("path")
        scoped = isinstance(fk, dict) and "scope" in fk
        cross = "-" in str(tgt).split(".")[0]
        add(comp, block, path, "fk", fk, "K7", "logical", cd,
            trigger="column:" + fk["scope"] if scoped else "",
            note=("cross-component" if cross else "intra-component") + (", scoped" if scoped else ""))
    if "model" in f:
        add(comp, block, path, "model", f["model"], "K7", "logical", cd, trigger="binding",
            note="cellid resolves in the exchange's model 1/2")
    if f.get("time_series"):
        add(comp, block, path, "time_series", True, "K7", "logical", cd, trigger="binding:TS6",
            note="value may name a time series")
    if f.get("dynamic"):
        add(comp, block, path, "dynamic", True, "K7", "logical", cd, trigger="option:auxiliary",
            note="array named by data; name must be in AUXILIARY")
    if "component" in f:
        add(comp, block, path, "component", f["component"], "K8", "logical", cd, trigger="binding",
            note="child component type")
    if "component_ftype" in f:
        add(comp, block, path, "component_ftype", f["component_ftype"], "K8", "logical", cd,
            trigger="binding", note="row's type column selects child component type")

    for n, sub in (f.get("fields") or {}).items():
        walk(comp, block, path + [n], sub, comp_dims, in_record or t in ("record", "union"))
    if isinstance(f.get("item"), dict):
        walk(comp, block, path, f["item"], comp_dims, True)
    for n, sub in (f.get("arms") or {}).items():
        walk(comp, block, path + [n], sub, comp_dims, True)


ncomp = 0
nfields = 0
for p in sorted(glob.glob(os.path.join(snap, "*.toml"))):
    d = tomllib.load(open(p, "rb"))
    comp = d["name"]
    ncomp += 1
    comp_dims = d.get("dims", {}) or {}
    if "parent" in d:
        add(comp, "", [], "parent", d["parent"], "K8", "logical", "config", trigger="binding",
            note="may be bound only under this parent type")
        add(comp, "", [], "multi", d.get("multi", False), "K8", "logical", "config",
            trigger="binding", note="cardinality per parent: many" if d.get("multi") else
            "cardinality per parent: at most one")
    for dn, dd in comp_dims.items():
        sc = dd.get("scope", "")
        add(comp, "", ["dims", dn], "dims", dd.get("value"), "K3", "logical", "config",
            trigger="binding:model" if sc == "model" else "",
            note="cross-component dimension" if sc == "model" else "local dimension")
    for b, bd in (d.get("blocks") or {}).items():
        h = bd.get("header")
        if isinstance(h, dict):
            add(comp, b, ["header"], "fill_forward", h.get("fill_forward", False), "K9", "logical",
                "data", note="period block carried forward" if h.get("fill_forward") else "")
        if bd.get("write_if_empty"):
            add(comp, b, [], "write_if_empty", True, "K1", "layout", "data")
        for n, f in (bd.get("fields") or {}).items():
            nfields += 1
            walk(comp, b, [b, n], f, comp_dims)

os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "dfn-constraints.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

print(f"{ncomp} components, {nfields} top-level fields, {len(rows)} constraint rows\n")
byk = collections.Counter((r["kind"], r["key"]) for r in rows)
for (k, key), n in sorted(byk.items()):
    print(f"  {k:5} {key:16} {n:5}")
print()
kind = collections.Counter(r["kind"] for r in rows)
print("by kind:", dict(sorted(kind.items())))
print("by level:", dict(collections.Counter(r["level"] for r in rows)))
print("shape classes:", dict(collections.Counter(r["note"] for r in rows if r["key"] == "shape")))
print("when triggers:", dict(collections.Counter(r["trigger"] for r in rows if r["key"] == "when")))
print("fk notes:", dict(collections.Counter(r["note"] for r in rows if r["key"] == "fk")))
print("multi:", dict(collections.Counter(r["note"] for r in rows if r["key"] == "multi")))
print("valid on:", dict(collections.Counter((r["block"], r["level"]) for r in rows if r["key"] == "valid")))
print("required by block:", dict(collections.Counter(r["block"] for r in rows if r["key"] == "required").most_common(12)))
