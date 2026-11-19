"""Check the [params] sketch against every real binding in the dev3 DFNs."""
import glob, os, sys, tomllib

SNAP = "/Users/wbonelli/dev/modflow-devtools-keyset-when/autotest/dfns/__snapshots__/v2.0.0.dev3"
dfns = {}
for p in glob.glob(f"{SNAP}/*.toml"):
    with open(p, "rb") as f:
        d = tomllib.load(f)
    dfns[d["name"]] = d

FORWARD = {"model1": {"type": "model", "from": {"exg-gwfgwf": "parent.model1"}},
           "model2": {"type": "model", "from": {"exg-gwfgwf": "parent.model2"}}}
ROW = {"model1": {"type": "model", "from": "row.exgmnamea"},
       "model2": {"type": "model", "from": "row.exgmnameb"}}
PARAMS = {
    "utl-spc": {"target": {"type": "package", "from": "row.pname"}},
    "utl-spca": {"target": {"type": ["gwf-rcha", "gwf-evta"], "from": "row.pname"}},
    "gwf-mvr": FORWARD,
    "gwf-gnc": FORWARD,
    "utl-obs": {"target": {"type": ["model", "package"], "from": "parent"}},
    **{e: ROW for e in ["exg-gwfgwf", "exg-gwtgwt", "exg-gwegwe", "exg-olfgwf", "exg-chfgwf"]},
}

def children(field):
    t = field.get("type")
    if t == "record":
        return field.get("fields", {})
    if t == "union":
        return field.get("arms", {})
    if t == "list":
        return {"<item>": field["item"]}
    return {}

def walk(fields, path, row=None):
    for name, f in fields.items():
        yield f"{path}.{name}", name, f, row
        kids = children(f)
        nextrow = kids if f.get("type") == "record" else row
        if f.get("type") == "list" and f["item"].get("type") == "record":
            nextrow = f["item"]["fields"]
        yield from walk(kids, f"{path}.{name}", nextrow)

def all_fields(d):
    for b, block in d.get("blocks", {}).items():
        yield from walk(block.get("fields", {}), b)

def admits(sel, c):
    sel = [sel] if isinstance(sel, str) else sel
    names = {c["name"], c.get("type"), c.get("subtype")}
    return any(t == "*" or t in names for t in sel)

def binders(name):
    """(binder, path, row columns) for every file field that can bind this component."""
    c = dfns[name]
    out = []
    for b, d in dfns.items():
        for path, fname, f, row in all_fields(d):
            if f.get("type") == "file" and f.get("component") and admits(f["component"], c):
                # a parent selector must admit the binder as well
                if c.get("parent") is None or admits(c["parent"], d):
                    out.append((b, path, row or {}))
    return out

problems = 0
for comp, params in PARAMS.items():
    bs = binders(comp)
    bnames = sorted({b for b, *_ in bs})
    print(f"{comp}: parent={dfns[comp].get('parent')!r}; {len(bnames)} binders")
    for pname, p in params.items():
        for b, path, row in bs:
            src = p["from"]
            if isinstance(src, dict):
                if b not in src:
                    print(f"  unset {comp}.{pname} under {b}")
                    continue
                src = src[b]
            for s in [src] if isinstance(src, str) else src:
                if s == "parent":
                    continue
                kind, _, col = s.partition(".")
                if kind == "row":
                    c = row.get(col)
                    if c is None:
                        print(f"  PROBLEM {comp}.{pname}: {b} {path}: no column {col}")
                        problems += 1
                    elif not c.get("fk"):
                        print(f"  PROBLEM {comp}.{pname}: {b}.{col} has no fk to follow")
                        problems += 1
                elif kind == "parent":
                    if col not in PARAMS.get(b, {}):
                        print(f"  PROBLEM {comp}.{pname}: {b} doesn't declare {col}")
                        problems += 1
        if isinstance(p["from"], dict):
            for arm in p["from"]:
                if arm not in bnames:
                    print(f"  PROBLEM {comp}.{pname}: from arm {arm} binds nothing")
                    problems += 1
    if comp in ("utl-spc", "utl-spca", "gwf-mvr", "gwf-gnc"):
        print("   ", [(b, path) for b, path, _ in bs])
print("problems:", problems)

print("\n-- sites")
rules, cells, fk_ts, when_mn = {}, [], [], []
for n, d in dfns.items():
    for path, name, f, _ in all_fields(d):
        fk = f.get("fk")
        if isinstance(fk, dict) and fk.get("rule"):
            rules.setdefault(fk["rule"], []).append(f"{n}:{path}")
        if f.get("model") in ("1", "2"):
            cells.append(f"{n}:{path}={f['model']}")
        if n in ("utl-ts", "utl-tas") and fk:
            fk_ts.append(f"{n}:{path}")
        if f.get("when") == "modelnames":
            when_mn.append(f"{n}:{path}")
for r, s in rules.items():
    print(r, len(s), s)
print("cellid model sites", len(cells)); print(*cells, sep="\n")
print("utl-ts/tas fks", fk_ts)
print("when=modelnames", when_mn)

arms = when = 0; comps = set()
obs_comps = [n for n, d in dfns.items() if d.get("observations")]
for n in obs_comps:
    for ot, o in dfns[n]["observations"].items():
        for a, af in o.get("arms", {}).items():
            if a == "boundname":
                arms += 1; comps.add(n); when += af.get("when") == "boundnames"
print("observation types' boundname arms", arms, "in", len(comps), "components; with when:", when)
has_opt = [n for n in comps if "boundnames" in dfns[n]["blocks"].get("options", {}).get("fields", {})]
print("of those, with a BOUNDNAMES option:", len(has_opt), "without:", sorted(comps - set(has_opt)))
print("components with observations", len(obs_comps), "; non-file-linked:", [n for n in obs_comps if not any(True for _ in [0]) ])
print("rcha/evta keys:", dfns["gwf-rcha"].get("keys"), dfns["gwf-evta"].get("keys"))
print("bound role:", sum("bound" in d.get("keys", {}) for d in dfns.values()))
print("exchanges:", sorted(n for n, d in dfns.items() if d.get("subtype") == "exchange"))
