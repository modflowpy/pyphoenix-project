"""Can inline text writes stream? Swap the template in memory (no repo change):
arrays loop at the top level of blocks.jinja instead of through the macros, the
way PR 66's template does. Compare peak against nlay, and output bytes against
the current writer, on the same data.
"""

import gc
import sys
import tempfile
import time
import tracemalloc
import warnings
from pathlib import Path

import dask
import dask.array as da
import jinja2
import numpy as np

from flopy4.mf6.codec import writer
from flopy4.mf6.gwf import Gwf, Npf
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation, Tdis
from flopy4.mf6.utils.grid import StructuredGrid
from flopy4.mf6.utils.time import Time

dask.config.set(scheduler="synchronous")
warnings.simplefilter("ignore")

CURRENT = writer._JINJA_ENV.loader


def array_lines(value, name, context):
    """The array's record, a piece at a time; None if not "internal" (those
    stay on the macros in this prototype)."""
    from flopy4.mf6.codec.writer.filters import array2chunks, array2string, iprn_option

    yield f" {name.upper()}\n"
    yield f" INTERNAL{iprn_option(value)}\n"
    first = True
    for chunk in array2chunks(value):
        if not first:
            yield "\n"
        first = False
        text = array2string(chunk, context.float_precision)
        yield "  " + text.replace("\n", "\n  ")
    yield "\n"


PROTO = """{% import 'macros.jinja' as macros with context %}
{% for block_name, block_value in blocks.items() %}
BEGIN {{ block_name|block_begin }}
{% for field_name, field_value in block_value.items() if (field_value) is not none -%}
{% if field_value|field_type == 'array' and field_value|array_how(context.use_netcdf, context.array_format) == 'internal' -%}
{% for piece in field_value|array_lines(field_name, context) -%}
{{ piece }}
{%- endfor %}

{%- else -%}
{{ macros.field(field_name, field_value) }}
{%- endif %}
{%- endfor %}
END {{ block_name|block_end }}

{% endfor %}
"""


def use(streaming):
    if streaming:
        writer._JINJA_ENV.loader = jinja2.ChoiceLoader(
            [jinja2.DictLoader({"blocks.jinja": PROTO}), CURRENT]
        )
    else:
        writer._JINJA_ENV.loader = CURRENT
    writer._JINJA_ENV.filters["array_lines"] = array_lines
    writer._JINJA_ENV.cache.clear()


def gen(b, block_info=None):
    if b.size == 0 or block_info is None:
        return b
    return np.random.default_rng(block_info[0]["chunk-location"]).random(b.shape) + 1


NR, NC = 200, 200
root = Path(tempfile.mkdtemp(dir=sys.argv[1]))
print(f"layer = {NR * NC * 8 / 1e6:.2f} MB; icelltype lazy; inline text")
for NL in (4, 16, 64):
    ws = root / f"n{NL}"
    ws.mkdir()
    k = da.zeros((NL, NR, NC), chunks=(1, NR, NC)).map_blocks(gen, dtype=float)
    ic = da.zeros((NL, NR, NC), chunks=(1, NR, NC), dtype=int)
    grid = StructuredGrid(
        nlay=NL,
        nrow=NR,
        ncol=NC,
        delr=np.ones(NC),
        delc=np.ones(NR),
        top=np.ones((NR, NC)),
        botm=np.stack([np.full((NR, NC), -float(i + 1)) for i in range(NL)]),
    )
    dims = {"nper": 1, **grid.dims}
    t = Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    gwf = Gwf(name="m", dis=grid, dims=dims)
    npf = Npf(parent=gwf, dims=dims, icelltype=ic, k=k)
    Simulation(
        name="s",
        tdis=Tdis.from_time(t),
        models=[gwf],
        solutiongroup=[Ims(linear_acceleration="cg")],
        workspace=ws,
    )
    out = {}
    for streaming in (False, True):
        use(streaming)
        npf.write()  # warm
        gc.collect()
        t0 = time.perf_counter()
        npf.write()
        secs = time.perf_counter() - t0
        tracemalloc.start()
        npf.write()
        _, p = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        out[streaming] = next(ws.rglob("*.npf")).read_bytes()
        mode = "streaming" if streaming else "current  "
        print(f"nlay={NL:<3} {mode} peak {p / 1e6:7.1f} MB  {secs:6.2f} s", flush=True)
    same = out[False] == out[True]
    print(f"  bytes identical: {same}")
    if not same:
        a, b = out[False], out[True]
        i = next((j for j in range(min(len(a), len(b))) if a[j] != b[j]), None)
        print(f"  lengths {len(a)} {len(b)}; first diff at {i}: {a[i-40:i+20]!r} vs {b[i-40:i+20]!r}")
