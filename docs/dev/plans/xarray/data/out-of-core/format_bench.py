"""Time array-to-text formatters on one array, single-threaded and by threads.

Each result is checked: values read back and compared, exactly or to the
format's precision. Formats a 2-D array, a line per row, as MF6 reads it.
"""

import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, sys.argv[1])

import numpy as np
import pandas as pd
from xarray_extras.kernels.np_to_csv_py import snprintcsvd

from flopy4.mf6.codec.writer.filters import array2string

NROW, NCOL = 1000, 1000
rng = np.random.default_rng(0)
# log-uniform like a K field, so values are full-precision and of varied size
A = 10 ** rng.uniform(-6, 3, size=(NROW, NCOL))


def kernel(arr, fmt):
    return snprintcsvd(arr, "\n" * arr.shape[0], " ", fmt, "")


def threaded(fmt, workers):
    parts = np.array_split(A, workers * 4, axis=0)
    with ThreadPoolExecutor(workers) as ex:
        return b"".join(ex.map(lambda p: kernel(p, fmt), parts))


def pandas_csv(fmt):
    buf = io.StringIO()
    pd.DataFrame(A).to_csv(buf, sep=" ", header=False, index=False, float_format=fmt)
    return buf.getvalue()


def repr_threaded(workers):
    parts = np.array_split(A, workers * 4, axis=0)
    with ThreadPoolExecutor(workers) as ex:
        return "\n".join(ex.map(array2string, parts))


CASES = [
    ("repr, current default (array2string)", lambda: array2string(A), "exact"),
    ("%.6e, current precision (savetxt)", lambda: array2string(A, 6), 6),
    ("pandas to_csv, float_format=None", lambda: pandas_csv(None), "exact"),
    ("pandas to_csv, %.6e", lambda: pandas_csv("%.6e"), 6),
    ("xarray-extras kernel, %.6e, 1 thread", lambda: kernel(A, "%.6e"), 6),
    ("xarray-extras kernel, %.16e, 1 thread", lambda: kernel(A, "%.16e"), "exact"),
    ("xarray-extras kernel, %.6e, 4 threads", lambda: threaded("%.6e", 4), 6),
    ("xarray-extras kernel, %.16e, 4 threads", lambda: threaded("%.16e", 4), "exact"),
    ("xarray-extras kernel, %.16e, 16 threads", lambda: threaded("%.16e", 16), "exact"),
    ("repr in threads (GIL control), 4 threads", lambda: repr_threaded(4), "exact"),
]

print(f"{A.size / 1e6:.0f}M float64, {A.nbytes / 1e6:.0f} MB")
base = None
for name, fn, check in CASES:
    times = []
    for _ in range(3):
        t = time.perf_counter()
        out = fn()
        times.append(time.perf_counter() - t)
    best = min(times)
    if isinstance(out, bytes):
        out = out.decode()
    back = np.array(out.split(), dtype=float)
    if back.size != A.size:
        verdict = f"WRONG COUNT {back.size}"
    elif check == "exact":
        verdict = "exact" if np.array_equal(back.reshape(A.shape), A) else "NOT EXACT"
    else:
        rel = np.abs(back.reshape(A.shape) - A) / A
        verdict = f"max rel err {rel.max():.1e}"
    lines = out.count("\n") + (0 if out.endswith("\n") else 1)
    base = base or best
    print(
        f"{name:<44} {best:7.3f} s  {base / best:5.1f}× default  "
        f"{len(out) / A.size:4.1f} B/val  {lines} lines  {verdict}",
        flush=True,
    )
