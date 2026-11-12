import builtins, os, sys, tempfile, shutil, warnings
from pathlib import Path
import numpy as np, flopy
warnings.simplefilter("ignore")
root=Path(tempfile.mkdtemp(dir=sys.argv[1])); ws=root/"src"; ws.mkdir()
nlay,nrow,ncol=2,5,5
sim=flopy.mf6.MFSimulation(sim_name="s",sim_ws=str(ws),verbosity_level=0)
flopy.mf6.ModflowTdis(sim,nper=2,perioddata=[(1,1,1)]*2); flopy.mf6.ModflowIms(sim)
g=flopy.mf6.ModflowGwf(sim,modelname="m")
flopy.mf6.ModflowGwfdis(g,nlay=nlay,nrow=nrow,ncol=ncol,top=1.,botm=[0.,-1.])
flopy.mf6.ModflowGwfic(g)
k=[{"filename":f"k{i}.txt","data":np.full((nrow,ncol),float(i+1)),"factor":1.0} for i in range(nlay)]
flopy.mf6.ModflowGwfnpf(g,k=k)
flopy.mf6.ModflowGwfwel(g,stress_period_data={0:{"filename":"wel0.txt","data":[((0,0,0),-1.0)]},1:{"filename":"wel1.txt","data":[((0,1,1),-2.0)]}})
sim.write_simulation(silent=True)
import struct
for i in range(nlay):
    with open(ws/f"bin{i}.bin","wb") as f:
        f.write(struct.pack("<iidd16siii",1,1,1.0,1.0,b"SS".rjust(16),ncol,nrow,i+1)); f.write(np.full((nrow,ncol),float(i+1)).tobytes())
(ws/"m.sto").write_text("BEGIN griddata\n ICONVERT\n  CONSTANT 0\n SS LAYERED\n  OPEN/CLOSE bin0.bin (BINARY)\n  OPEN/CLOSE bin1.bin (BINARY)\n SY\n  CONSTANT 0.1\nEND griddata\nBEGIN period 1\n STEADY-STATE\nEND period 1\n")
t=(ws/"m.nam").read_text().replace("END packages"," STO6  m.sto  sto\nEND packages"); (ws/"m.nam").write_text(t)
print("files:",sorted(p.name for p in ws.iterdir() if p.suffix in(".txt",".bin")))
EXT=("k0.txt","k1.txt","bin0.bin","bin1.bin","wel0.txt","wel1.txt")
log=[]; real=builtins.open
def spy(f,*a,**k):
    n=os.path.basename(str(f))
    if n in EXT: log.append(n)
    return real(f,*a,**k)
builtins.open=spy
def take():
    c={n:log.count(n) for n in EXT if n in log}; log.clear(); return c
for lazy in (False,True):
    print(f"\n=== lazy_io={lazy}")
    w=root/f"run{lazy}"; shutil.copytree(ws,w); log.clear()
    s=flopy.mf6.MFSimulation.load(sim_ws=str(w),verbosity_level=0,lazy_io=lazy); m=s.get_model("m")
    print("after load:           ",take())
    a=m.npf.k.array; print("npf.k.array 1st:      ",take(),type(a).__name__,a.ravel()[0])
    m.npf.k.array; print("npf.k.array 2nd:      ",take())
    m.sto.ss.array; print("sto.ss.array:         ",take())
    m.wel.stress_period_data.get_data(); print("wel get_data:         ",take())
    (w/"k0.txt").write_text("\n".join(" ".join(["99.0"]*ncol) for _ in range(nrow))+"\n")
    log.clear()
    try: print("k after file edited:  ",m.npf.k.array.ravel()[0],take())
    except Exception as e: print("k after file edited:  ",type(e).__name__,str(e).splitlines()[-1][:110],take())
    print("  source k0.txt head:",repr((w/"k0.txt").read_text()[:30]))
    out=root/f"out{lazy}"; s.set_sim_path(str(out)); log.clear(); s.write_simulation(silent=True)
    print("write to new ws:      ",take()); print("  files there:",sorted(p.name for p in out.iterdir() if p.suffix in(".txt",".bin")), "k0 first:",(out/"k0.txt").read_text().split()[:1] if (out/"k0.txt").exists() else None)
    print("  OUTNPF:",repr((out/"m.npf").read_text()[-220:])); print("  OUTWEL:",repr((out/"m.wel").read_text()[-160:]))
    print("  out all files:",sorted(str(x.relative_to(root)) for x in out.rglob("*"))[:12])
    print("  sim_path:",s.sim_path, "| src npf:",repr((w/"m.npf").read_text()[-150:]))
    print("  out .npf k records:",[l.strip() for l in (out/"m.npf").read_text().splitlines() if "open/close" in l.lower()])
    print("  out .wel records:",[l.strip() for l in (out/"m.wel").read_text().splitlines() if "open/close" in l.lower()])
    w2=root/f"miss{lazy}"; shutil.copytree(ws,w2); (w2/"k0.txt").unlink(); (w2/"wel0.txt").unlink()
    try:
        s2=flopy.mf6.MFSimulation.load(sim_ws=str(w2),verbosity_level=0,lazy_io=lazy); print("load, missing files:   no error")
        try: s2.get_model("m").npf.k.array; print("access missing k:      no error")
        except Exception as e: print("access missing k:     ",type(e).__name__)
    except Exception as e: print("load, missing files:  ",type(e).__name__,str(e)[:80].replace("\n"," "))
shutil.rmtree(root,ignore_errors=True)
