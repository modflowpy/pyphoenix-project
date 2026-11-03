"""Extract and cluster MF6 error/warning sites (see docs/dev/plans/dfn-spec/constraint-audit.md).

Usage: python mf6_sites.py <modflow6 src dir> <out dir>
Writes mf6-checks.csv (one row per store_error / store_warning site) and prints tallies.
store_error_filename / store_error_unit are follow-ups that attach a file to earlier errors;
they are counted but not treated as sites.
"""

import collections
import csv
import os
import re
import sys

src, out = sys.argv[1:3]

CALL = re.compile(r"^\s*(?:if\s*\(.*\)\s*)?call\s+(store_error|store_warning)\s*\(", re.I)
FOLLOW = re.compile(r"call\s+(store_error_filename|store_error_unit)\b", re.I)
MSGSTART = re.compile(r"write\s*\(\s*(errmsg|warnmsg|msg|ermsg|errmsgr|wmsg)\b|^\s*(errmsg|warnmsg|msg|ermsg)\s*=", re.I)
ROUTINE = re.compile(r"^\s*(?:(?:recursive|pure|elemental|module)\s+)*(subroutine|function)\s+(\w+)", re.I)
STR = re.compile(r"'((?:[^']|'')*)'|\"((?:[^\"]|\"\")*)\"")

# Normalised message -> cluster. First match wins; order matters.
CLUSTERS = [
    ("not-input", r"could not open|error opening|unit number|already open|file .*not (found|exist)|"
                  r"iostat|allocat|programming error|internal error|not implemented|"
                  r"memory manager|mem_|should not happen|developer|unknown memory|"
                  r"did not converge|failed to converge|convergence failure|nonconvergence|"
                  r"petsc|mpi|binary file|header|end of file|reached end|eof|program(mer)? error|"
                  r"error reading|netcdf library|read_line|insufficient|needs new case|aborted|went dry|"
                  r"adjusted theta|must be overridden|maxobstypes"),
    ("binding-context", r"exchange|solution|\\brank\\b|connect(ed|ing)? .*model|model .* (connected|in different)|"
                        r"flow model|gwf model|gwfbudget|fmi"),
    ("enum", r"must be (one of |either )?['\"]?[A-Z_]+['\"]?,? (or|,)|unknown .* specified|unsupported|"
             r"must be 1 .* or 2|looking for .* found"),
    ("unknown-keyword", r"unknown .*(keyword|option|block|tag|record)|unrecognized|not recognized|"
                        r"invalid (keyword|option|tag)|not a valid (keyword|option)"),
    ("block-structure", r"block|begin|end .* expected|required .* not found|not found .* block"),
    ("deprecated", r"deprecat|no longer supported|removed|obsolete"),
    ("duplicate", r"duplicat|more than once|already (been )?(defined|specified|exists|used)|unique|"
                  r"multiple .* (same|specified)"),
    ("not-found-ref", r"not found|does not exist|could not find|cannot find|no .* (named|with name)|"
                      r"invalid .* name|not (a )?valid .* name|unknown .* name|"
                      r"(model|package|boundname|time.?series|feature|reach|lake|well) .* not"),
    ("cellid-grid", r"cell ?id|cellid|node .* (outside|out of|invalid|exceed)|outside (of )?(the )?(model|grid)|"
                    r"idomain|inactive|reduced node|user node"),
    ("range-count", r"less than (1|one) or greater than|was not specified or was specified incorrectly|"
                    r"at most|exceed|greater than (the )?(number|max|nbound|maxbound)|maximum number|"
                    r"out of range|outside .* range|must be between|must be (<|less than or equal) .*(n|max)|"
                    r"number of .* (must|should) (equal|match|be)|does not (equal|match)|mismatch|"
                    r"too (many|few)|not enough|invalid number"),
    ("sign-value", r"must be (greater|less|positive|negative|non-?negative|>|<|=|zero|between)|"
                   r"(cannot|can not|may not) be (negative|zero|less|greater)|"
                   r"less than (zero|0)|negative|<= *0|< *0|> *0|positive|non-?zero|zero"),
    ("geometry", r"top|bot(tom)?|thickness|elevation|vertex|vertices|clockwise|area|length|"
                 r"symmetr|ihc|ja |\bja\b|connection|cl12|hwva|angldegx|cell2d"),
    ("option-coherence", r"specified but .* not (specified|provided|active)|not (specified|provided) .* but|"
                         r"must be .* when|when using|missing|cannot be (used|specified|combined)|can not be (used|specified)|"
                         r"only (be )?(used|specified|valid|available|supported)|requires|required when|"
                         r"must (also )?be (specified|used|active|activated|on)|not compatible|incompatible|"
                         r"not (allowed|supported|permitted)|mutually exclusive|in conjunction|"
                         r"must be specified|is not active|not activated|is activated"),
    ("temporal", r"period|kper|nper|stress period|time ?step|\btime\b|tsmult|perlen|delt|ats"),
    ("type-parse", r"invalid|not (a )?valid|could not (read|parse|convert)|expected|"
                   r"must be an? (integer|real|number|string)"),
]
CLUSTERS = [(n, re.compile(p, re.I)) for n, p in CLUSTERS]


def family(path):
    p = path.replace("\\", "/")
    for key, fam in [("Idm/", "idm"), ("Utilities/", "utilities"), ("Solution/", "solution"),
                     ("Exchange/", "exchange"), ("Timing/", "timing"), ("Distributed/", "distributed")]:
        if key in p:
            return fam
    m = re.search(r"Model/(\w+)/", p)
    if m:
        return m.group(1)
    return "top"


def join(lines):
    """Join Fortran continuation lines, including strings continued with &...&."""
    s = "\n".join(lines)
    s = re.sub(r"&[ \t]*(?:![^\n]*)?\n[ \t]*&", "", s)   # string continuation
    s = re.sub(r"&[ \t]*(?:![^\n'\"]*)?\n", " ", s)       # statement continuation
    return s


def literals(lines, fmts=None):
    s = join(lines)
    parts = [m.group(1) or m.group(2) or "" for m in STR.finditer(s)]
    if fmts:
        for name in re.findall(r"write\s*\(\s*\w+\s*,\s*(\w+)\s*\)", s, re.I):
            if name.lower() in fmts:
                parts.insert(0, fmts[name.lower()])
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


FMT = re.compile(r"character\s*\(\s*len\s*=\s*\*\s*\)\s*,\s*parameter\s*::\s*(\w+)\s*=", re.I)


def formats(text):
    """Named format constants in a file: name -> literal text."""
    out = {}
    for i, ln in enumerate(text):
        m = FMT.search(ln)
        if m:
            j, block = i, [ln[m.end():]]
            while block[-1].rstrip().endswith("&") and j + 1 < len(text):
                j += 1
                block.append(text[j])
            out[m.group(1).lower()] = literals(block)
    return out


KIND = {"not-input": "-", "binding-context": "K8", "enum": "K2", "unknown-keyword": "K1",
        "block-structure": "K1", "deprecated": "K1", "duplicate": "K6", "not-found-ref": "K7",
        "cellid-grid": "K7", "range-count": "K3", "sign-value": "K2", "geometry": "K10",
        "option-coherence": "K5", "temporal": "K9", "type-parse": "K1", "unclassified": "?"}

rows = []
follow = collections.Counter()
for root, _, files in os.walk(src):
    for fn in files:
        if not fn.lower().endswith((".f90",)):
            continue
        path = os.path.join(root, fn)
        rel = os.path.relpath(path, src)
        text = open(path, errors="replace").read().splitlines()
        routine = ""
        fmts = formats(text)
        for i, ln in enumerate(text):
            code = ln.split("!")[0] if "'" not in ln and '"' not in ln else ln
            m = ROUTINE.match(code)
            if m and not re.match(r"^\s*end\b", code, re.I):
                routine = m.group(2)
            fm = FOLLOW.search(code)
            if fm:
                follow[fm.group(1).lower()] += 1
                continue
            cm = CALL.match(code)
            if not cm:
                continue
            # Gather the call statement (continuation lines).
            j = i
            stmt = [text[j]]
            while stmt[-1].rstrip().endswith("&") and j + 1 < len(text):
                j += 1
                stmt.append(text[j])
            msg = literals(stmt, fmts)
            # Look back for the message-building statement if the call passes a variable.
            if len(msg) < 15:
                for k in range(i - 1, max(i - 25, -1), -1):
                    if CALL.match(text[k]) or ROUTINE.match(text[k]):
                        break
                    if MSGSTART.search(text[k]):
                        block = text[k:i]
                        msg = (literals(block, fmts) + " " + msg).strip()
                        break
            cluster = "unclassified"
            for name, rx in CLUSTERS:
                if rx.search(msg):
                    cluster = name
                    break
            rows.append(dict(file=rel, line=i + 1, routine=routine, family=family(rel),
                             call=cm.group(1).lower(), cluster=cluster, kind=KIND[cluster], message=msg[:300]))

os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "mf6-checks.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(sorted(rows, key=lambda r: (r["family"], r["file"], r["line"])))

print(f"{len(rows)} sites; follow-ups: {dict(follow)}")
print("by call:", dict(collections.Counter(r["call"] for r in rows)))
print("empty message:", sum(1 for r in rows if not r["message"]))
print("\nby cluster:")
for c, n in collections.Counter(r["cluster"] for r in rows).most_common():
    print(f"  {c:18} {n:5}")
print("\nby tentative kind:", dict(sorted(collections.Counter(r["kind"] for r in rows).items())))
print("\nby family:")
for c, n in collections.Counter(r["family"] for r in rows).most_common():
    print(f"  {c:18} {n:5}")
