
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