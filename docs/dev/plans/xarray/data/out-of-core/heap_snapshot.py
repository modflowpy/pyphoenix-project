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
NR,NC,NL=200,200,32
state={"n":0,"snap":None}
def gen(b, block_info=None):
    if b.size==0 or block_info is None: return b
    state["n"]+=1
    if state["n"]==NL and tracemalloc.is_tracing(): state["snap"]=tracemalloc.take_snapshot()
    return np.random.default_rng(block_info[0]["chunk-location"]).random(b.shape)+1
root=Path(tempfile.mkdtemp(dir=sys.argv[1])); ws=root/"w"; ws.mkdir()
k=da.zeros((NL,NR,NC),chunks=(1,NR,NC)).map_blocks(gen,dtype=float)
grid=StructuredGrid(nlay=NL,nrow=NR,ncol=NC,delr=np.ones(NC),delc=np.ones(NR),top=np.ones((NR,NC)),botm=np.stack([np.full((NR,NC),-float(i+1)) for i in range(NL)]))
dims={"nper":1,**grid.dims}; t=Time(perlen=[1.0],nstp=[1],tsmult=[1.0])
gwf=Gwf(name="m",dis=grid,dims=dims); npf=Npf(parent=gwf,dims=dims,icelltype=0,k=k)
Simulation(name="s",tdis=Tdis.from_time(t),models=[gwf],solutiongroup=[Ims(linear_acceleration="cg")],workspace=ws)
print("k type/dims in object:",type(npf.k).__name__,getattr(npf.k,"shape",None))
for f,ctx in [("inline",None),("open/close",WriteContext(array_format="open/close")),("binary",WriteContext(array_format="binary"))]:
    wr=(lambda: npf.write(context=ctx)) if ctx else npf.write
    wr(); gc.collect(); state.update(n=0,snap=None); tracemalloc.start(8); wr(); _,p=tracemalloc.get_traced_memory(); tracemalloc.stop()
    print(f"\n{f}: peak {p/1e6:.1f} MB; k {NL*NR*NC*8/1e6:.1f} MB; held at last block:")
    for s in state["snap"].statistics("lineno")[:5]:
        fr=s.traceback[0]; print(f"  {s.size/1e6:7.1f} MB  {'/'.join(Path(fr.filename).parts[-3:])}:{fr.lineno}")
shutil.rmtree(root,ignore_errors=True)
