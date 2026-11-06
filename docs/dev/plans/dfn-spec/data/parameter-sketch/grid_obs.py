"""Observation by name on grid packages, which have no BOUNDNAMES option."""
import os, shutil, subprocess, sys
ROOT = sys.argv[1]
BINS = {"release db59037": sys.argv[2], "fcheck 7f69b525e9": sys.argv[3]}
N = 3.0e30
def arr(vals): return "  constant %s" % vals
CASES = {
 "rcha": ("RCH6", "READASARRAYS", "rch", "  recharge\n    constant 1.0E-3\n"),
 "evta": ("EVT6", "READASARRAYS", "evt", "  surface\n    constant 10.0\n  rate\n    constant 1.0E-3\n  depth\n    constant 5.0\n"),
 "chdg": ("CHD6", "READARRAYGRID", "chd", "  head\n    internal factor 1.0\n    3.0E+30 3.0E+30 11.0\n"),
 "drng": ("DRN6", "READARRAYGRID", "drn", "  elev\n    internal factor 1.0\n    3.0E+30 3.0E+30 9.0\n  cond\n    internal factor 1.0\n    3.0E+30 3.0E+30 1.0\n"),
 "ghbg": ("GHB6", "READARRAYGRID", "ghb", "  bhead\n    internal factor 1.0\n    3.0E+30 3.0E+30 9.0\n  cond\n    internal factor 1.0\n    3.0E+30 3.0E+30 1.0\n"),
 "rivg": ("RIV6", "READARRAYGRID", "riv", "  stage\n    internal factor 1.0\n    3.0E+30 3.0E+30 9.0\n  cond\n    internal factor 1.0\n    3.0E+30 3.0E+30 1.0\n  rbot\n    internal factor 1.0\n    3.0E+30 3.0E+30 8.0\n"),
 "welg": ("WEL6", "READARRAYGRID", "wel", "  q\n    internal factor 1.0\n    3.0E+30 3.0E+30 -1.0E-3\n"),
}
def write(d, ftype, opt, obstype, period, ident):
    os.makedirs(d, exist_ok=True)
    w = lambda n, t: open(os.path.join(d, n), "w").write(t)
    w("mfsim.nam", "BEGIN timing\n  TDIS6 m.tdis\nEND timing\nBEGIN models\n  gwf6 m.nam m\nEND models\nBEGIN exchanges\nEND exchanges\nBEGIN solutiongroup 1\n  ims6 m.ims m\nEND solutiongroup 1\n")
    w("m.tdis", "BEGIN dimensions\n  NPER 1\nEND dimensions\nBEGIN perioddata\n  1.0 1 1.0\nEND perioddata\n")
    w("m.ims", "BEGIN nonlinear\n  OUTER_MAXIMUM 50\nEND nonlinear\nBEGIN linear\n  INNER_MAXIMUM 50\nEND linear\n")
    w("m.nam", f"BEGIN packages\n  DIS6 m.dis dis\n  IC6 m.ic ic\n  NPF6 m.npf npf\n  CHD6 m.chd fix\n  {ftype} m.tgt tgt\nEND packages\n")
    w("m.dis", "BEGIN dimensions\n  NLAY 1\n  NROW 1\n  NCOL 3\nEND dimensions\nBEGIN griddata\n  DELR\n    constant 10.0\n  DELC\n    constant 10.0\n  TOP\n    constant 10.0\n  BOTM\n    constant 0.0\nEND griddata\n")
    w("m.ic", "BEGIN griddata\n  STRT\n    constant 10.0\nEND griddata\n")
    w("m.npf", "BEGIN griddata\n  ICELLTYPE\n    constant 0\n  K\n    constant 1.0\nEND griddata\n")
    w("m.chd", "BEGIN dimensions\n  MAXBOUND 1\nEND dimensions\nBEGIN period 1\n  1 1 1 10.0\nEND period 1\n")
    w("m.tgt", f"BEGIN options\n  {opt}\n  OBS6 FILEIN m.obs\nEND options\nBEGIN period 1\n{period}END period 1\n")
    w("m.obs", f"BEGIN continuous FILEOUT m.obs.csv\n  a {obstype} {ident}\nEND continuous\n")
for name, (ftype, opt, obstype, period) in CASES.items():
    for label, ident in (("cell", "1 1 3"), ("name", "somename")):
        d = os.path.join(ROOT, name, label)
        shutil.rmtree(d, ignore_errors=True)
        write(d, ftype, opt, obstype, period, ident)
        for bname, b in BINS.items():
            for f in ("mfsim.lst", "m.obs.csv"):
                try: os.remove(os.path.join(d, f))
                except FileNotFoundError: pass
            r = subprocess.run([b], cwd=d, capture_output=True, text=True, timeout=60)
            out = r.stdout + r.stderr
            normal = "Normal termination" in out
            msg = ""
            for l in out.splitlines():
                if any(k in l for k in ("ERROR", "above upper bound", "invalid", "Index", "Fortran runtime")):
                    msg = l.strip()[:110]; break
            csv = ""
            p = os.path.join(d, "m.obs.csv")
            if os.path.exists(p): csv = open(p).read().splitlines()[-1]
            print(f"{name:5} {label:5} {bname:18} rc={r.returncode:<3} normal={normal!s:5} csv={csv:32} {msg}")
