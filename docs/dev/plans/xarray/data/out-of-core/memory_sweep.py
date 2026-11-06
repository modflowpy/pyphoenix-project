import gc, sys, tempfile, tracemalloc, warnings, shutil
from pathlib import Path
import dask, dask.array as da, numpy as np
from flopy4.mf6.gwf import Gwf, Npf
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation, Tdis
from flopy4.mf6.utils.grid import StructuredGrid
from flopy4.mf6.utils.time import Time
from flopy4.mf6.write_context import WriteContext
dask.config.set(scheduler="synchronous"); warnings.simplefilter("ignore")
def gen(b, block_info=None):
    if b.size==0 or block_info is None: return b
    return np.random.default_rng(block_info[0]["chunk-location"]).random(b.shape)+1
NR,NC=200,200
root=Path(tempfile.mkdtemp(dir=sys.argv[1]))
print(f"layer = {NR*NC*8/1e6:.2f} MB of float64; other griddata constant")
for NL in (4,16,64):
    N=NL*NR*NC; ws=root/f"n{NL}"; ws.mkdir()
    k=da.zeros((NL,NR,NC),chunks=(1,NR,NC)).map_blocks(gen,dtype=float)
    grid=StructuredGrid(nlay=NL,nrow=NR,ncol=NC,delr=np.ones(NC),delc=np.ones(NR),top=np.ones((NR,NC)),botm=np.stack([np.full((NR,NC),-float(i+1)) for i in range(NL)]))
    dims={"nper":1,**grid.dims}; t=Time(perlen=[1.0],nstp=[1],tsmult=[1.0])
    gwf=Gwf(name="m",dis=grid,dims=dims); npf=Npf(parent=gwf,dims=dims,icelltype=da.zeros((NL,NR,NC),chunks=(1,NR,NC),dtype=int),k=k)
    Simulation(name="s",tdis=Tdis.from_time(t),models=[gwf],solutiongroup=[Ims(linear_acceleration="cg")],workspace=ws)
    for f,ctx in [("inline",None),("open/close",WriteContext(array_format="open/close")),("binary",WriteContext(array_format="binary"))]:
        wr=(lambda: npf.write(context=ctx)) if ctx else npf.write
        wr(); gc.collect(); tracemalloc.start(); wr(); _,p=tracemalloc.get_traced_memory(); tracemalloc.stop()
        print(f"nlay={NL:<3} k={N*8/1e6:6.1f} MB {f:<11} peak {p/1e6:7.1f} MB  ({p/(N*8):5.2f}× k)")
    print("   files:",sorted(x.name for x in ws.rglob("*") if x.is_file() and "k" in x.name)[:4], "...", len([x for x in ws.rglob("*") if x.is_file() and x.suffix in(".bin",".txt")]))
shutil.rmtree(root,ignore_errors=True)
