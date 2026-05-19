
## ff_write  (commit def1808, 2026-05-19 13:43:54)

| Variant | min (s) | mean (s) | runs |
|---------|--------:|---------:|-----:|
| **frenchman-flat** | | | |
| &nbsp;&nbsp;flopy4 list  (WEL) | 0.204 | 0.214 | 5 |
| &nbsp;&nbsp;flopy4 welg_ascii (WELG, 7.5M elem) | 1.039 | 1.052 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_base (WEL+NetCDF arrays) | 0.277 | 0.368 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_mesh (WELG+layered NC) | 0.279 | 0.319 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_structured (WELG+CF NC) | 0.192 | 0.221 | 5 |
| &nbsp;&nbsp;flopy3 list  (WEL) | 0.855 | 0.885 | 5 |

## test1000_write  (commit def1808, 2026-05-19 13:51:52)

| Variant | min (s) | mean (s) | runs |
|---------|--------:|---------:|-----:|
| **sparse (WEL+CHD)** | | | |
| &nbsp;&nbsp;flopy4 list        (WEL+CHD) | 0.220 | 0.230 | 5 |
| &nbsp;&nbsp;flopy4 grid ASCII  (WELG+CHDG, 1.74M sparse) | 0.225 | 0.226 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_mesh (WELG+CHDG) | 1.780 | 1.953 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_struct (WELG+CHDG) | 0.100 | 0.105 | 5 |
| &nbsp;&nbsp;flopy3 list        (WEL+CHD) | 1.818 | 1.860 | 5 |
| **dense uniform RCH** | | | |
| &nbsp;&nbsp;flopy4 list        (Rch, 1.74M entries) | 21.932 | 22.088 | 5 |
| &nbsp;&nbsp;flopy4 array ASCII (Rcha, CONSTANT) | 0.237 | 0.239 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_mesh (Rcha, CONSTANT) | 1.707 | 1.844 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_struct (Rcha, CONSTANT) | 0.127 | 0.139 | 5 |
| &nbsp;&nbsp;flopy3 list        (Rch) | 11.496 | 11.987 | 5 |
| &nbsp;&nbsp;flopy3 array       (Rcha, CONSTANT) | 1.879 | 1.897 | 5 |
| **dense heterogeneous RCH** | | | |
| &nbsp;&nbsp;flopy4 list        (Rch, 1.74M entries) | 23.855 | 24.302 | 5 |
| &nbsp;&nbsp;flopy4 array ASCII (Rcha, per-cell) | 0.870 | 0.879 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_mesh (Rcha, per-cell) | 1.764 | 1.811 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_struct (Rcha, per-cell) | 0.129 | 0.134 | 5 |
| &nbsp;&nbsp;flopy3 list        (Rch) | 11.012 | 11.282 | 5 |
| &nbsp;&nbsp;flopy3 array       (Rcha, per-cell) | 5.367 | 5.390 | 5 |

## test1005_write  (commit def1808, 2026-05-19 13:52:28)

| Variant | min (s) | mean (s) | runs |
|---------|--------:|---------:|-----:|
| **WEL+CHD+RCHA** | | | |
| &nbsp;&nbsp;flopy4 list  (WEL+CHD+RCHA) | 0.686 | 0.706 | 5 |
| &nbsp;&nbsp;flopy3 list  (WEL+CHD+RCHA) | 4.435 | 4.483 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_mesh  (WELG+CHDG+RCHA) | 0.279 | 0.350 | 5 |
| &nbsp;&nbsp;flopy4 netcdf_struct (WELG+CHDG+RCHA) | 0.100 | 0.104 | 5 |