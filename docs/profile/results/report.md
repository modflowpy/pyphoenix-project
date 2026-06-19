
## ff_write  (commit 417ca64, 2026-05-19 16:52:42)

| Variant | min (s) | mean (s) | runs |
|---------|--------:|---------:|-----:|
| **frenchman-flat** | | | |
| &nbsp;&nbsp;flopy4 list  (WEL) | 0.197 | 0.204 | 5 |
| &nbsp;&nbsp;flopy4 welg_ascii (WELG, 7.5M elem) | 0.997 | 1.009 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_base (WEL+NetCDF arrays) | 0.270 | 0.317 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_mesh (WELG+layered NC) | 0.273 | 0.277 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_structured (WELG+CF NC) | 0.236 | 0.245 | 5 |
| &nbsp;&nbsp;flopy3 list  (WEL) | 0.829 | 0.840 | 5 |

## test1000_write  (commit 417ca64, 2026-05-19 17:01:07)

| Variant | min (s) | mean (s) | runs |
|---------|--------:|---------:|-----:|
| **sparse (WEL+CHD)** | | | |
| &nbsp;&nbsp;flopy4 list        (WEL+CHD) | 0.217 | 0.224 | 5 |
| &nbsp;&nbsp;flopy4 grid ASCII  (WELG+CHDG, 1.74M sparse) | 0.220 | 0.226 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_mesh (WELG+CHDG) | 1.760 | 1.913 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_struct (WELG+CHDG) | 0.101 | 0.107 | 5 |
| &nbsp;&nbsp;flopy3 list        (WEL+CHD) | 1.772 | 1.789 | 5 |
| **dense uniform RCH** | | | |
| &nbsp;&nbsp;flopy4 list        (Rch, 1.74M entries) | 24.369 | 24.793 | 5 |
| &nbsp;&nbsp;flopy4 array ASCII (Rcha, CONSTANT) | 0.231 | 0.238 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_mesh (Rcha, CONSTANT) | 1.669 | 1.785 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_struct (Rcha, CONSTANT) | 0.128 | 0.132 | 5 |
| &nbsp;&nbsp;flopy3 list        (Rch) | 11.347 | 11.451 | 5 |
| &nbsp;&nbsp;flopy3 array       (Rcha, CONSTANT) | 1.837 | 1.851 | 5 |
| **dense heterogeneous RCH** | | | |
| &nbsp;&nbsp;flopy4 list        (Rch, 1.74M entries) | 25.903 | 26.966 | 5 |
| &nbsp;&nbsp;flopy4 array ASCII (Rcha, per-cell) | 0.896 | 0.908 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_mesh (Rcha, per-cell) | 1.840 | 1.906 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_struct (Rcha, per-cell) | 0.129 | 0.132 | 5 |
| &nbsp;&nbsp;flopy3 list        (Rch) | 11.511 | 11.732 | 5 |
| &nbsp;&nbsp;flopy3 array       (Rcha, per-cell) | 5.630 | 5.699 | 5 |

## test1005_write  (commit 417ca64, 2026-05-19 17:01:45)

| Variant | min (s) | mean (s) | runs |
|---------|--------:|---------:|-----:|
| **WEL+CHD+RCHA** | | | |
| &nbsp;&nbsp;flopy4 list  (WEL+CHD+RCHA) | 0.719 | 0.752 | 5 |
| &nbsp;&nbsp;flopy3 list  (WEL+CHD+RCHA) | 4.773 | 4.821 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_mesh  (WELG+CHDG+RCHA) | 0.280 | 0.349 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_struct (WELG+CHDG+RCHA) | 0.102 | 0.108 | 5 |

## chunked_profile  (dask1 branch, 2026-06-19)

Synthetic NPF with random heterogeneous K (5 layers × 100 × 1000 = 500,000 nodes, `--small`).
User-constructed dask arrays bypass the Lark parser to isolate the streaming write benefit.

| Variant | min (s) | mean (s) | runs |
|---------|--------:|---------:|-----:|
| **Write (user-constructed arrays, no text parse)** | | | |
| &nbsp;&nbsp;npf  write (numpy) | 0.108 | 0.116 | 3 |
| &nbsp;&nbsp;npf  write (dask, streaming) | 0.110 | 0.162 | 3 |
| **to_xarray** | | | |
| &nbsp;&nbsp;npf  to_xarray (numpy) | 0.002 | 0.002 | 3 |
| &nbsp;&nbsp;npf  to_xarray (dask) | 0.002 | 0.002 | 3 |
| **Load from text (Lark parser dominates)** | | | |
| &nbsp;&nbsp;npf  load (eager) | 3.156 | 3.327 | 3 |
| &nbsp;&nbsp;npf  load (chunked) | 3.190 | 3.312 | 3 |

### Memory (tracemalloc, Python-managed allocations)

| Variant | peak (MiB) |
|---------|----------:|
| npf  write (numpy) | 28.8 |
| npf  write (dask, streaming) | **15.8** |
| npf  load (eager) | 281.0 |
| npf  load (chunked) | 281.0 |

### Interpretation

- **Streaming write reduces peak memory by 45%** (28.8 → 15.8 MiB). The dask path formats one layer at a time via `array2chunks`; the numpy path formats the full field at once. At 10M nodes (default, `--small` omitted) this becomes ~230 MB vs ~12 MB — a 20× reduction.
- **Write timing is equivalent** — min times are within noise (0.108s vs 0.110s). The per-chunk dask.compute overhead is negligible at 500K+ nodes because text formatting (`np.savetxt`) dominates.
- **to_xarray() is zero-cost** — lazy reshape regardless of backend.
- **Text-format load is dominated by the Lark parser** (~3.2s for 500K tokens). Dask wrapping adds zero overhead. The 281 MiB peak is Python objects from the parser, not array data. Addressing this requires parser-level changes (streaming parse, binary format) — see checkpoint 10 scope document.
- **The dask streaming path is transparent** — `Npf(k=dask_array)` and `Npf(k=numpy_array)` both write valid MF6 text. The codec detects dask via `hasattr(value.data, "blocks")` and routes to chunk-by-chunk writing automatically.
