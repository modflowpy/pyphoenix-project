"""Merge labels into options.csv, write labelled CSV/MD and a tally.

Usage: python label.py <dir with options.csv>
category: layout | logical | output | mixed
tags: binding, schema (comma-separated)
evidence: mem (catalog), desc (DFN description), src:<file> (MF6 source), inv (api_overhaul
internal inventory)
"""

import collections
import csv
import os
import sys

d = sys.argv[1]
rows = list(csv.DictReader(open(os.path.join(d, "options.csv"))))

NPF = "src:gwf-npf.f90,gwf-tvk.f90"
CSUB = "src:gwf-csub.f90"

L = {}


def lab(names, cat, tags="", ev="desc", notes=""):
    for n in names.split():
        L[n] = (cat, tags, ev, notes)


# ---------------- layout ----------------
lab("readasarrays", "layout", "", "mem+desc",
    "Runtime memory of RCH/RCHA converges. Partial lens: list→array fails for >1 entry "
    "per column; array form has no boundnames.")
lab("readarraygrid", "layout", "", "desc",
    "Grid-array encoding of a stress list (CHDG etc.). Partial lens like READASARRAYS.")
lab("nc_filerecord", "layout", "", "mem+desc",
    "Names the NetCDF file that NETCDF-tagged arrays are read from. Where data lives, "
    "not what it is.")
lab("modelnames", "layout", "", "desc",
    "MVR: package references written model-qualified. Reference encoding only.")
lab("complexity", "layout", "", "desc",
    "IMS/PTS: a preset that expands to solver parameter defaults. Expanding it is "
    "lossless. The parameters themselves are logical.")
lab("k22overk k33overk", "layout", "", NPF,
    "K22/K33 given as ratio to K. Applied at load (npf:1957,1987) and to TVK values "
    "against the then-current K11 (tvk:239-250). Lens spans NPF+TVK; needs TVK schedule.")
lab("storagecoefficient", "layout", "", "src:GwfStorageUtils.f90 SsCapacity",
    "SS given as S; thickness=1 instead of top-bot (static). Lens spans STO+TVS. "
    "Runtime memory holds the undecoded value: decoding is lazy.")
lab("length_conversion time_conversion", "layout", "", "src:swf-dfw.f90:344",
    "Constant factor in Manning's eq. (unitconv=L^(1/3)*T). Re-encode n'=n/unitconv. "
    "Lens spans DFW+CXS.")
lab("unit_conversion", "layout", "", "desc",
    "SFR: same constant Manning factor as DFW length/time_conversion.")
lab("flow_reduction_length", "layout", "", "src:gwf-wel.f90",
    "AUTO_FLOW_REDUCE given as length instead of fraction of (static) cell thickness. "
    "Per-cell lens: one length ≠ one fraction across cells, so a uniform scalar may "
    "not re-encode to a scalar. Partial lens.")
lab("cell_fraction", "layout", "", CSUB,
    "Interbed THICK given as fraction of cell thickness (static).")
lab("specified_initial_interbed_state specified_initial_preconsolidation_stress "
    "specified_initial_delay_head", "layout", "", CSUB + ":4206-4240",
    "Absolute vs offset-from-initial-state. Computed lens: needs initial effective "
    "stress (from STRT, TOP/BOT, geostatic) to re-encode.")
lab("initial_preconsolidation_head", "layout", "", CSUB + ":4208-4218",
    "PCS given as head, not stress. Computed lens (geostatic stress).")
lab("compression_indices", "layout", "", CSUB + ":4264",
    "CR/CC vs SSE/SSI. MF6 converts SS to CR at init using void ratio and initial "
    "effective stress: computed lens. Check behaviour under HEAD_BASED before relying.")
lab("auxmultname", "logical", "schema", "src:gwf-wel.f90:766,gwf-rch.f90:271,gwf-chd.f90:427",
    "Was the closest call (layout). Relabelled by the derivation axis: bound = value × aux "
    "is evaluated at every use against the current aux value, which may be a TS, so the "
    "rule itself is model content (dynamic derivation). Same structure as AUXDEPTHNAME. "
    "Snapshot re-encoding (multiply in) is still possible but loses the rule.")

# ---------------- mixed ----------------
lab("head_based", "mixed", "", CSUB + ":622-624,670",
    "Formulation switch (lhead_based: logical) that also sets IPCH, i.e. preconsolidation "
    "given as head (the encoding INITIAL_PRECONSOLIDATION_HEAD selects). Two concepts on "
    "one keyword; the encoding part cannot be chosen separately.")

# ---------------- output (run directives) ----------------
out_simple = """save_flows print_input print_flows export_array_ascii export_array_netcdf
budget_filerecord budgetcsv_filerecord grb_filerecord nogrb list concentration_filerecord
stage_filerecord temperature_filerecord package_convergence_filerecord print_concentration
print_temperature nc_mesh2d_filerecord nc_structured_filerecord qoutflow_filerecord
qoutflowprintrecord save_velocity afrcsv_filerecord csv_inner_output_filerecord
csv_outer_output_filerecord csv_output_filerecord head_filerecord print_stage
sorbate_filerecord track_filerecord trackcsv_filerecord cim_filerecord cimprintrecord
compaction_coarse_filerecord compaction_elastic_filerecord compaction_filerecord
compaction_inelastic_filerecord compaction_interbed_filerecord concentrationprintrecord
density_filerecord headprintrecord mfrcsv_filerecord print_head save_saturation
save_specific_discharge straincg_filerecord strainib_filerecord temperatureprintrecord
track_dropped track_exit track_release track_subfeature_exit track_terminate
track_timesrecord track_timestep track_usertime track_weaksink viscosity_filerecord
wc_filerecord zdisplacement_filerecord digits print_option chunk_face chunk_time chunk_x
chunk_y chunk_z deflate shuffle modflow6_attr_off"""
lab(out_simple, "output", "", "desc+inv")
L["save_specific_discharge"] = ("output", "", "mem+desc",
                                "Also forces spdis to be computed; computing it does not "
                                "change the solution.")
L["track_timesrecord"] = ("output", "", "desc", "Values of an output directive.")
lab("memory_print_option profile_option dev_log_mpi print_table dev_dump_event_trace",
    "output", "", "desc", "Run directive: logging/profiling, not a file of results.")
lab("maxerrors nocheck vertical_offset_tolerance coordinate_check_method", "output", "",
    "desc+src:Disu.f90:477",
    "Run directive: input validation. Changes whether the run errors, not what it "
    "computes.")
lab("continue", "output", "", "desc",
    "Run directive: policy on non-convergence. Closest to logical of the run directives.")
lab("hpc_filerecord", "output", "binding", "desc",
    "Run directive: parallel partitioning. Results invariant up to round-off.")
lab("obs_filerecord", "output", "binding", "desc",
    "Observations only produce output. [observations] in dev3 already declares the "
    "binding parameter on the target.")
lab("ncf_filerecord", "output", "binding", "desc",
    "NCF is mostly NetCDF output config (chunking, deflate); its WKT is logical "
    "metadata and duplicates DIS CRS.")
lab("track_timesfilerecord", "layout", "", "desc",
    "External file for the tracking-times values. The option is layout; the values are "
    "output directives.")

# ---------------- logical: bindings ----------------
lab("ts_filerecord tas_filerecord", "logical", "binding", "desc",
    "Not layout: TS/TAS interpolate within a period, which period data cannot express "
    "without changing TDIS.")
lab("tvk_filerecord tvs_filerecord ats_filerecord gnc_filerecord mvr_filerecord "
    "mvt_filerecord mve_filerecord", "logical", "binding", "desc")
lab("flow_package_name gwfmodelname1 gwfmodelname2", "logical", "binding", "desc")
lab("flow_package_auxiliary_name", "logical", "binding schema", "desc",
    "References a column of another package's table.")
lab("mover", "logical", "binding", "desc",
    "Target-side declaration that the package takes part in an MVR relation.")
lab("release_timesfilerecord", "layout", "", "mem+desc",
    "External file for the release-times values.")

# ---------------- logical: schema ----------------
lab("auxiliary", "logical", "schema", "desc", "ADD COLUMN.")
lab("boundnames", "logical", "schema", "desc", "Identity column; target of obs/mvr keys.")
lab("surf_rate_specified", "logical", "schema", "mem+desc", "Adds PETM0 column.")
lab("auxdepthname", "logical", "schema", "desc",
    "Unlike AUXMULTNAME, gives an aux column a new physical role (drain scaling depth).")
lab("sorption first_order_decay zero_order_decay zero_order_decay_solid "
    "zero_order_decay_water", "logical", "schema", "mem+desc",
    "Process switch that also decides which griddata arrays exist.")
lab("temperature_species_name", "logical", "schema", "mem+desc",
    "Key reference to a PACKAGEDATA row (intra-component reference).")
lab("flowing_wells", "logical", "", "desc")

# ---------------- logical: metadata ----------------
lab("angrot crs length_units xorigin yorigin wkt time_units start_date_time", "logical",
    "", "desc", "Descriptive metadata: no runtime effect, kept by any conversion.")

# ---------------- logical: settings (everything else defaults here) ----------------
lab("local_z", "logical", "", "src:prt-prp.f90:706",
    "Looks like a coordinate encoding, but scales by simulated saturation at release "
    "time (gwfsat), so it is a statement about the model, not a static lens.")
lab("fixed_conductance", "logical", "", "src:exg-swfgwf.f90:539",
    "Switches off depth smoothing and wetted-perimeter area: different physics, not "
    "a re-encoding.")
lab("thickstrt", "logical", "", "desc",
    "Thickness from STRT-BOT: not re-encodable by editing TOP, which has other uses.")
lab("release_timesrecord", "logical", "", "desc",
    "Values. Has an alternative encoding (RELEASETIMES block / file) to check in step 2.")
lab("dependent_variable_scaling", "logical", "", "mem+desc",
    "Numerics; effect on results is round-off only. Borderline with run directive.")

# ---------------- derivation axis ----------------
# Does the option declare that a quantity is computed from other quantities?
#   none:    no derivation (encoding choice, value, switch, reference, directive)
#   static:  every input to the rule is fixed once its value is written, so materialising
#            the result is lossless. Basis: where MF6 evaluates it.
#   dynamic: an input can change during the run (TS/TAS, TVK/TVS, simulated state), and MF6
#            re-evaluates the rule, so the rule is model content.
DERIV = {
    # static
    "k22overk": ("static", "decoded at load (npf:1987) and on each TVK write against K11 at "
                           "that time (tvk:239); later K11 changes do not propagate"),
    "k33overk": ("static", "as k22overk (npf:1957, tvk:250)"),
    "storagecoefficient": ("static", "decoded at use (SsCapacity) but against top-bot, which "
                                     "is fixed"),
    "cell_fraction": ("static", "fraction of fixed cell thickness"),
    "flow_reduction_length": ("static", "length vs fraction of fixed cell thickness"),
    "length_conversion": ("static", "constant factor"),
    "time_conversion": ("static", "constant factor"),
    "unit_conversion": ("static", "constant factor"),
    "complexity": ("static", "preset expanded to solver defaults once"),
    "specified_initial_interbed_state": ("static", "offset from initial state, computed once"),
    "specified_initial_preconsolidation_stress": ("static", "offset from initial state, "
                                                            "computed once"),
    "specified_initial_delay_head": ("static", "offset from initial state, computed once"),
    "initial_preconsolidation_head": ("static", "head to stress via initial geostatic stress"),
    "compression_indices": ("static", "SS to CR/CC via initial void ratio and stress"),
    "head_based": ("static", "forces IPCH (preconsolidation as head): the static part of a "
                             "formulation switch"),
    "thickstrt": ("static", "thickness from STRT - BOT, computed once; no input column holds "
                            "the result, so it stays logical"),
    # dynamic
    "auxmultname": ("dynamic", "value × aux at every use (wel:766, rch:271, chd:427); aux may "
                               "be a TS"),
    "auxdepthname": ("dynamic", "depth-scaled conductance from aux in drn_cf/drn_fc each "
                                "iteration"),
    "ts_filerecord": ("dynamic", "values interpolated from series each time step"),
    "tas_filerecord": ("dynamic", "arrays interpolated from series each time step"),
    "local_z": ("dynamic", "scaled by simulated saturation at release (prt-prp:706)"),
}
unknown = set(DERIV) - {r["name"] for r in rows}
assert not unknown, unknown

for r in rows:
    n = r["name"]
    if n in L:
        r["category"], r["tags"], r["evidence"], r["notes"] = L[n]
    else:
        r["category"], r["tags"], r["evidence"], r["notes"] = (
            "logical", "", "mem+desc" if r["memory"] else "desc",
            "Model or numerics setting.")
    r["derivation"], r["derivation_basis"] = DERIV.get(n, ("none", ""))

unknown = set(L) - {r["name"] for r in rows}
assert not unknown, unknown

with open(os.path.join(d, "options-labelled.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

by = collections.defaultdict(list)
occ = collections.Counter()
for r in rows:
    by[r["category"]].append(r["name"])
    occ[r["category"]] += int(r["count"])
tags = collections.Counter(t for r in rows for t in r["tags"].split())

with open(os.path.join(d, "options-labelled.md"), "w") as fh:
    fh.write("# Option labels (dev3)\n\n| category | distinct | % | occurrences |\n"
             "|---|---|---|---|\n")
    for c in ("layout", "logical", "output", "mixed"):
        fh.write(f"| {c} | {len(by[c])} | {100*len(by[c])/len(rows):.1f} | {occ[c]} |\n")
    fh.write(f"\nTags: {dict(tags)}\n\n")
    fh.write("Derivation (rows: category, columns: derivation):\n\n"
             "| category | none | static | dynamic |\n|---|---|---|---|\n")
    for c in ("layout", "logical", "output", "mixed"):
        dc = collections.Counter(r["derivation"] for r in rows if r["category"] == c)
        fh.write(f"| {c} | {dc['none']} | {dc['static']} | {dc['dynamic']} |\n")
    fh.write("\n")
    show = ["name", "count", "category", "tags", "derivation", "evidence", "notes",
            "derivation_basis", "components"]
    fh.write("| " + " | ".join(show) + " |\n|" + "---|" * len(show) + "\n")
    order = {"mixed": 0, "layout": 1, "output": 2, "logical": 3}
    for r in sorted(rows, key=lambda r: (order[r["category"]], -int(r["count"]), r["name"])):
        fh.write("| " + " | ".join(str(r[c]).replace("|", "\\|") for c in show) + " |\n")

for c in ("layout", "logical", "output", "mixed"):
    print(f"{c:8} {len(by[c]):4} {100*len(by[c])/len(rows):5.1f}% occ={occ[c]}")
print("tags", dict(tags))
for c in ("layout", "logical", "output", "mixed"):
    dc = collections.Counter(r["derivation"] for r in rows if r["category"] == c)
    print(f"derivation {c:8} " + " ".join(f"{k}={dc[k]}" for k in ("none", "static", "dynamic")))
print("dynamic:", sorted(r["name"] for r in rows if r["derivation"] == "dynamic"))
print("defaulted to logical:", sorted(n for n in (r["name"] for r in rows) if n not in L))
