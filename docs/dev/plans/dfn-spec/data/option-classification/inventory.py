"""Inventory of DFN options fields with memory-catalog mappings.

Usage: python inventory.py <snapshot dir> <out dir>
"""

import collections
import csv
import glob
import os
import re
import sys
import tomllib

snap, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)


def first_sentence(s):
    s = " ".join((s or "").split())
    m = re.match(r"(.+?\.)(\s|$)", s)
    return (m.group(1) if m else s)[:200]


def subnames(f):
    """All nested field names under a field (record/list items)."""
    names = []
    for key in ("fields",):
        for n, sf in (f.get(key) or {}).items():
            names.append(n)
            names += subnames(sf)
    item = f.get("item")
    if item:
        names.append(item.get("name", ""))
        names += subnames(item)
    return names


def form(f):
    t = f.get("type")
    if t == "keyword":
        return "keyword"
    if t in ("record", "list") or f.get("item"):
        return "record"
    return "value"


rows = {}
ncomp = 0
nfields = 0
for path in sorted(glob.glob(os.path.join(snap, "*.toml"))):
    d = tomllib.load(open(path, "rb"))
    comp = d.get("name") or os.path.basename(path)[:-5]
    ncomp += 1
    opts = (d.get("blocks") or {}).get("options", {}).get("fields", {})
    mem = d.get("memory") or {}
    src = collections.defaultdict(list)
    for var, v in mem.items():
        s = v.get("source")
        for x in [s] if isinstance(s, str) else (s or []):
            flags = []
            if v.get("readonly"):
                flags.append("ro")
            si = v.get("set_in")
            if si:
                flags.append("set_in=" + (si if isinstance(si, str) else "/".join(si)))
            src[x].append(f"{var}({','.join(flags)})" if flags else var)
    for name, f in opts.items():
        nfields += 1
        r = rows.setdefault(
            name,
            dict(name=name, comps=[], types=set(), forms=set(), descs={}, mem=set(),
                 targets=set()),
        )
        r["comps"].append(comp)
        r["types"].add(f.get("type", ""))
        r["forms"].add(form(f))
        desc = f.get("description") or ""
        if not desc:
            # records: use the description of the filename/value subfield
            for sf in (f.get("fields") or (f.get("item") or {}).get("fields") or {}).values():
                if sf.get("type") != "keyword" and sf.get("description"):
                    desc = sf["description"]
                    break
        r["descs"].setdefault(first_sentence(desc), []).append(comp)
        for n in [name] + subnames(f):
            for m in src.get(n, []):
                r["mem"].add(f"{comp}:{m}")
        # file references / bindings
        for sf in [f] + list((f.get("fields") or {}).values()) + list(
            ((f.get("item") or {}).get("fields") or {}).values()
        ):
            if sf.get("type") == "file":
                r["targets"].add(f"{sf.get('direction', '?')}:{sf.get('component', '?')}")

out_rows = []
for r in sorted(rows.values(), key=lambda r: (-len(r["comps"]), r["name"])):
    comps = r["comps"]
    descs = sorted(r["descs"].items(), key=lambda kv: -len(kv[1]))
    mem_vars = sorted({m.split(":", 1)[1] for m in r["mem"]})
    mem_comps = len({m.split(":", 1)[0] for m in r["mem"]})
    out_rows.append(
        dict(
            name=r["name"],
            count=len(comps),
            components=" ".join(comps) if len(comps) <= 10 else f"({len(comps)})",
            type="/".join(sorted(r["types"])),
            form="/".join(sorted(r["forms"])),
            files="; ".join(sorted(r["targets"])),
            description=descs[0][0],
            desc_variants=len(descs),
            memory=" ".join(mem_vars),
            memory_coverage=f"{mem_comps}/{len(set(comps))}" if mem_vars else "",
            category="",
            tags="",
            evidence="",
            notes="",
        )
    )

cols = list(out_rows[0].keys())
with open(os.path.join(out, "options.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    w.writerows(out_rows)

with open(os.path.join(out, "options.md"), "w") as fh:
    fh.write(
        f"# Options inventory (dev3)\n\n{ncomp} components, {nfields} option fields, "
        f"{len(out_rows)} distinct names.\n\n"
    )
    show = ["name", "count", "form", "files", "memory", "memory_coverage", "description"]
    fh.write("| " + " | ".join(show) + " |\n|" + "---|" * len(show) + "\n")
    for r in out_rows:
        fh.write("| " + " | ".join(str(r[c]).replace("|", "\\|") for c in show) + " |\n")

print(ncomp, "components", nfields, "fields", len(out_rows), "distinct")
print("singletons", sum(1 for r in out_rows if r["count"] == 1))
print("with memory", sum(1 for r in out_rows if r["memory"]))
