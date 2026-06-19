"""
Frenchman Flat read-time profiling: lazy vs. eager, HDS and CBC.

Uses the pre-built binary output files in test/__compare__/test_examples/.
Run the frenchman-flat simulation first if those files are absent.

Variants
--------
hds  lazy open            open_hds() — builds dask graph, no compute
hds  first timestep       da[0].compute() on a pre-opened array
hds  full compute         open_hds(...).compute() — all timesteps
hds  chunk sweep          full compute across time_chunks=[1, 5, all]
cbc  lazy open            open_cbc() — builds dask graph, no compute
cbc  full compute         open_cbc(...) + ds.compute() on every variable

Pass --memory to add tracemalloc peak-heap measurements for each variant.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _timer import (
    make_parser,
    profile_memory,
    report,
    sweep_chunks,
    time_reads,
    write_results,
)

from flopy4.mf6.utils.cbc_reader import open_cbc
from flopy4.mf6.utils.heads_reader import open_hds

DATA = Path(__file__).parent.parent.parent / "test" / "__compare__" / "test_examples"
HDS = DATA / "frenchman-flat.hds"
CBC = DATA / "frenchman-flat.cbc"
GRB = DATA / "frenchman-flat.grb"

OUT = Path(__file__).parent / "results" / "ff"


def main():
    args = make_parser("Frenchman Flat read-time profiling").parse_args()
    N, include_slow, do_memory = args.runs, args.include_slow, args.memory
    sections = []

    if not HDS.exists():
        print(
            f"\n[SKIP] {HDS} not found.\n"
            "       Run the frenchman-flat model (docs/profile/ff_write.py) first,\n"
            "       or copy binary output to test/__compare__/test_examples/."
        )
        return

    import os

    hds_mb = os.path.getsize(HDS) / 1e6
    cbc_mb = os.path.getsize(CBC) / 1e6 if CBC.exists() else 0
    print(
        f"\n{'=' * 60}\n"
        f"frenchman-flat read profiling  n={N}\n"
        f"  HDS {hds_mb:.1f} MB   CBC {cbc_mb:.1f} MB\n"
        f"{'=' * 60}"
    )

    # ── HDS timing variants ───────────────────────────────────────────────────
    timing_results = []

    timing_results.append(
        report(
            "hds  lazy open",
            time_reads(lambda: open_hds(HDS, GRB), N, "hds lazy open", include_slow),
        )
    )

    # Pre-open once; measure only the compute step.
    _da = open_hds(HDS, GRB)
    timing_results.append(
        report(
            "hds  first timestep .compute()",
            time_reads(lambda: _da[0].compute(), N, "hds t0 compute", include_slow),
        )
    )

    timing_results.append(
        report(
            "hds  full .compute()",
            time_reads(lambda: open_hds(HDS, GRB).compute(), N, "hds full compute", include_slow),
        )
    )

    # ── HDS chunk sweep ───────────────────────────────────────────────────────
    # Determine total timestep count from the lazy array already open.
    ntime = _da.sizes["time"]
    chunk_sizes = sorted({1, 5, ntime})  # de-dup in case ntime <= 5

    print(f"\n{'─' * 60}")
    print(f"HDS chunk sweep  (ntime={ntime}, chunk_sizes={chunk_sizes})")
    print(f"{'─' * 60}")

    sweep_results = sweep_chunks(
        fn_factory=lambda cs: lambda: open_hds(HDS, GRB, time_chunks=cs).compute(),
        chunk_sizes=chunk_sizes,
        label_prefix="hds  full compute",
        n=max(N, 3),
        include_slow=include_slow,
    )
    timing_results.extend(sweep_results)

    # ── CBC timing variants ───────────────────────────────────────────────────
    if CBC.exists():
        timing_results.append(
            report(
                "cbc  lazy open",
                time_reads(lambda: open_cbc(CBC, GRB), N, "cbc lazy open", include_slow),
            )
        )

        timing_results.append(
            report(
                "cbc  full .compute()",
                time_reads(
                    lambda: open_cbc(CBC, GRB).compute(),
                    N,
                    "cbc full compute",
                    include_slow,
                ),
            )
        )

    sections.append({"name": "frenchman-flat-reads", "results": timing_results})

    # ── Memory profiling ──────────────────────────────────────────────────────
    if do_memory:
        print(f"\n{'─' * 60}")
        print("Peak memory (tracemalloc — Python allocations only)")
        print(f"{'─' * 60}")
        mem_results = []
        mem_results.append(profile_memory(lambda: open_hds(HDS, GRB), "hds  lazy open"))
        mem_results.append(
            profile_memory(lambda: open_hds(HDS, GRB).compute(), "hds  full .compute()")
        )
        if CBC.exists():
            mem_results.append(profile_memory(lambda: open_cbc(CBC, GRB), "cbc  lazy open"))
            mem_results.append(
                profile_memory(lambda: open_cbc(CBC, GRB).compute(), "cbc  full .compute()")
            )
        sections.append({"name": "frenchman-flat-reads-memory", "results": mem_results})

    if args.output:
        write_results(args.output, "ff_read", N, sections)


if __name__ == "__main__":
    main()
