"""
Chunked/dask profiling: streaming write vs eager write.

Constructs a large NPF directly with dask or numpy arrays (bypassing the
Lark text parser) and measures the write path. This isolates the dask
streaming benefit: the codec writer's array2chunks iterates dask blocks one
layer at a time, never materializing the full array simultaneously.

Also profiles text-format load to confirm dask wrapping adds zero overhead.

Variants
--------
**Write (user-constructed arrays):**
  npf  write (numpy)         construct Npf with numpy K, write to text
  npf  write (dask)          construct Npf with dask K, write to text (streaming)

**Load from text file:**
  npf  load (eager)          Package.load(path, dims)
  npf  load (chunked)        Package.load(path, dims, chunks="auto")

**xarray views:**
  npf  to_xarray (numpy)     npf.to_xarray() on numpy-backed package
  npf  to_xarray (dask)      npf.to_xarray() on dask-backed package

Pass --memory to add tracemalloc peak-heap measurements.
Pass --small to use a 500K-node grid (quick smoke test).
"""

import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from _timer import make_parser, profile_memory, report, time_reads, write_results


def main():
    parser = make_parser("Chunked/dask streaming write profiling")
    parser.add_argument(
        "--small",
        action="store_true",
        help="Use 500K nodes (5L×100R×1000C) for quick validation instead of 10M",
    )
    args = parser.parse_args()
    N, include_slow, do_memory = args.runs, args.include_slow, args.memory
    sections = []

    if args.small:
        nlay, nrow, ncol = 5, 100, 1000
    else:
        nlay, nrow, ncol = 20, 500, 1000

    nodes = nlay * nrow * ncol
    ncpl = nrow * ncol
    dims = {"nlay": nlay, "nrow": nrow, "ncol": ncol, "nodes": nodes, "ncpl": ncpl}
    field_mb = nodes * 8 / 1e6
    layer_mb = ncpl * 8 / 1e6

    print(f"\n{'=' * 60}")
    print(f"chunked profile  ({nlay}L×{nrow}R×{ncol}C = {nodes:,} nodes)  n={N}")
    print(f"  field size: {field_mb:.1f} MB   layer size: {layer_mb:.1f} MB")
    print(f"{'=' * 60}")

    from flopy4.mf6.codec import dumps
    from flopy4.mf6.converter import COMPONENT_CONVERTER
    from flopy4.mf6.gwf.npf import Npf

    # ── Construct packages with numpy vs dask arrays ──────────────────────────
    rng = np.random.default_rng(42)
    k_numpy = rng.uniform(0.001, 100.0, size=nodes)

    import dask.array as da

    k_dask = da.from_array(k_numpy.reshape(nlay, ncpl), chunks=(1, ncpl)).reshape(-1)

    npf_numpy = Npf(k=k_numpy, icelltype=np.zeros(nodes, dtype=np.int64), dims=dims)
    npf_dask = Npf(k=k_dask, icelltype=np.zeros(nodes, dtype=np.int64), dims=dims)

    # ── Write timing (the key comparison) ─────────────────────────────────────
    print(f"\n{'─' * 60}")
    print("Write timing (user-constructed arrays, no text parse)")
    print(f"{'─' * 60}")
    timing_results = []

    timing_results.append(
        report(
            "npf  write (numpy)",
            time_reads(
                lambda: dumps(COMPONENT_CONVERTER.unstructure(npf_numpy)),
                N,
                "write numpy",
                include_slow,
            ),
        )
    )

    timing_results.append(
        report(
            "npf  write (dask, streaming)",
            time_reads(
                lambda: dumps(COMPONENT_CONVERTER.unstructure(npf_dask)),
                N,
                "write dask",
                include_slow,
            ),
        )
    )

    # ── to_xarray timing ─────────────────────────────────────────────────────
    print(f"\n{'─' * 60}")
    print("to_xarray timing")
    print(f"{'─' * 60}")

    timing_results.append(
        report(
            "npf  to_xarray (numpy)",
            time_reads(npf_numpy.to_xarray, N, "to_xarray numpy", include_slow),
        )
    )

    timing_results.append(
        report(
            "npf  to_xarray (dask)",
            time_reads(npf_dask.to_xarray, N, "to_xarray dask", include_slow),
        )
    )

    # ── Load from text (confirms zero dask overhead) ──────────────────────────
    print(f"\n{'─' * 60}")
    print("Load from text file (Lark parser dominates — confirms zero dask overhead)")
    print(f"{'─' * 60}")

    # Write a text file to load from
    tmp = tempfile.mkdtemp(prefix="chunked_profile_")
    npf_path = Path(tmp) / "synthetic.npf"
    text = dumps(COMPONENT_CONVERTER.unstructure(npf_numpy))
    npf_path.write_text(text)
    file_mb = npf_path.stat().st_size / 1e6
    print(f"  NPF file: {file_mb:.0f} MB")

    timing_results.append(
        report(
            "npf  load (eager)",
            time_reads(lambda: Npf.load(npf_path, dims=dims), N, "load eager", include_slow),
        )
    )

    timing_results.append(
        report(
            "npf  load (chunked)",
            time_reads(
                lambda: Npf.load(npf_path, dims=dims, chunks="auto"),
                N,
                "load chunked",
                include_slow,
            ),
        )
    )

    sections.append({"name": "chunked-profile", "results": timing_results})

    # ── Memory profiling ──────────────────────────────────────────────────────
    if do_memory:
        print(f"\n{'─' * 60}")
        print("Peak memory (tracemalloc — Python allocations only)")
        print(f"{'─' * 60}")
        mem_results = []
        mem_results.append(
            profile_memory(
                lambda: dumps(COMPONENT_CONVERTER.unstructure(npf_numpy)),
                "npf  write (numpy)",
            )
        )
        mem_results.append(
            profile_memory(
                lambda: dumps(COMPONENT_CONVERTER.unstructure(npf_dask)),
                "npf  write (dask, streaming)",
            )
        )
        mem_results.append(
            profile_memory(lambda: Npf.load(npf_path, dims=dims), "npf  load (eager)")
        )
        mem_results.append(
            profile_memory(
                lambda: Npf.load(npf_path, dims=dims, chunks="auto"), "npf  load (chunked)"
            )
        )
        sections.append({"name": "chunked-profile-memory", "results": mem_results})

    if args.output:
        write_results(args.output, "chunked_profile", N, sections)

    # Cleanup
    import shutil

    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
