# Option labels (dev3)

| category | distinct | % | occurrences |
|---|---|---|---|
| layout | 20 | 8.9 | 38 |
| logical | 121 | 54.0 | 437 |
| output | 82 | 36.6 | 559 |
| mixed | 1 | 0.4 | 1 |

Tags: {'binding': 17, 'schema': 12}

Derivation (rows: category, columns: derivation):

| category | none | static | dynamic |
|---|---|---|---|
| layout | 6 | 14 | 0 |
| logical | 115 | 1 | 5 |
| output | 82 | 0 | 0 |
| mixed | 0 | 1 | 0 |

| name | count | category | tags | derivation | evidence | notes | derivation_basis | components |
|---|---|---|---|---|---|---|---|---|
| head_based | 1 | mixed |  | static | src:gwf-csub.f90:622-624,670 | Formulation switch (lhead_based: logical) that also sets IPCH, i.e. preconsolidation given as head (the encoding INITIAL_PRECONSOLIDATION_HEAD selects). Two concepts on one keyword; the encoding part cannot be chosen separately. | forces IPCH (preconsolidation as head): the static part of a formulation switch | gwf-csub |
| length_conversion | 5 | layout |  | static | src:swf-dfw.f90:344 | Constant factor in Manning's eq. (unitconv=L^(1/3)*T). Re-encode n'=n/unitconv. Lens spans DFW+CXS. | constant factor | chf-dfw gwf-lak gwf-sfr olf-dfw swf-dfw |
| readarraygrid | 5 | layout |  | none | desc | Grid-array encoding of a stress list (CHDG etc.). Partial lens like READASARRAYS. |  | gwf-chdg gwf-drng gwf-ghbg gwf-rivg gwf-welg |
| time_conversion | 5 | layout |  | static | src:swf-dfw.f90:344 | Constant factor in Manning's eq. (unitconv=L^(1/3)*T). Re-encode n'=n/unitconv. Lens spans DFW+CXS. | constant factor | chf-dfw gwf-lak gwf-sfr olf-dfw swf-dfw |
| nc_filerecord | 3 | layout |  | none | mem+desc | Names the NetCDF file that NETCDF-tagged arrays are read from. Where data lives, not what it is. |  | gwe-nam gwf-nam gwt-nam |
| readasarrays | 3 | layout |  | none | mem+desc | Runtime memory of RCH/RCHA converges. Partial lens: list→array fails for >1 entry per column; array form has no boundnames. |  | gwf-evta gwf-rcha utl-spca |
| complexity | 2 | layout |  | static | desc | IMS/PTS: a preset that expands to solver parameter defaults. Expanding it is lossless. The parameters themselves are logical. | preset expanded to solver defaults once | sln-ims sln-pts |
| flow_reduction_length | 2 | layout |  | static | src:gwf-wel.f90 | AUTO_FLOW_REDUCE given as length instead of fraction of (static) cell thickness. Per-cell lens: one length ≠ one fraction across cells, so a uniform scalar may not re-encode to a scalar. Partial lens. | length vs fraction of fixed cell thickness | gwf-wel gwf-welg |
| cell_fraction | 1 | layout |  | static | src:gwf-csub.f90 | Interbed THICK given as fraction of cell thickness (static). | fraction of fixed cell thickness | gwf-csub |
| compression_indices | 1 | layout |  | static | src:gwf-csub.f90:4264 | CR/CC vs SSE/SSI. MF6 converts SS to CR at init using void ratio and initial effective stress: computed lens. Check behaviour under HEAD_BASED before relying. | SS to CR/CC via initial void ratio and stress | gwf-csub |
| initial_preconsolidation_head | 1 | layout |  | static | src:gwf-csub.f90:4208-4218 | PCS given as head, not stress. Computed lens (geostatic stress). | head to stress via initial geostatic stress | gwf-csub |
| k22overk | 1 | layout |  | static | src:gwf-npf.f90,gwf-tvk.f90 | K22/K33 given as ratio to K. Applied at load (npf:1957,1987) and to TVK values against the then-current K11 (tvk:239-250). Lens spans NPF+TVK; needs TVK schedule. | decoded at load (npf:1987) and on each TVK write against K11 at that time (tvk:239); later K11 changes do not propagate | gwf-npf |
| k33overk | 1 | layout |  | static | src:gwf-npf.f90,gwf-tvk.f90 | K22/K33 given as ratio to K. Applied at load (npf:1957,1987) and to TVK values against the then-current K11 (tvk:239-250). Lens spans NPF+TVK; needs TVK schedule. | as k22overk (npf:1957, tvk:250) | gwf-npf |
| modelnames | 1 | layout |  | none | desc | MVR: package references written model-qualified. Reference encoding only. |  | gwf-mvr |
| release_timesfilerecord | 1 | layout |  | none | mem+desc | External file for the release-times values. |  | prt-prp |
| specified_initial_delay_head | 1 | layout |  | static | src:gwf-csub.f90:4206-4240 | Absolute vs offset-from-initial-state. Computed lens: needs initial effective stress (from STRT, TOP/BOT, geostatic) to re-encode. | offset from initial state, computed once | gwf-csub |
| specified_initial_interbed_state | 1 | layout |  | static | src:gwf-csub.f90:4206-4240 | Absolute vs offset-from-initial-state. Computed lens: needs initial effective stress (from STRT, TOP/BOT, geostatic) to re-encode. | offset from initial state, computed once | gwf-csub |
| specified_initial_preconsolidation_stress | 1 | layout |  | static | src:gwf-csub.f90:4206-4240 | Absolute vs offset-from-initial-state. Computed lens: needs initial effective stress (from STRT, TOP/BOT, geostatic) to re-encode. | offset from initial state, computed once | gwf-csub |
| storagecoefficient | 1 | layout |  | static | src:GwfStorageUtils.f90 SsCapacity | SS given as S; thickness=1 instead of top-bot (static). Lens spans STO+TVS. Runtime memory holds the undecoded value: decoding is lazy. | decoded at use (SsCapacity) but against top-bot, which is fixed | gwf-sto |
| track_timesfilerecord | 1 | layout |  | none | desc | External file for the tracking-times values. The option is layout; the values are output directives. |  | prt-oc |
| unit_conversion | 1 | layout |  | static | desc | SFR: same constant Manning factor as DFW length/time_conversion. | constant factor | gwf-sfr |
| save_flows | 79 | output |  | none | desc+inv |  |  | (79) |
| print_input | 78 | output |  | none | desc+inv |  |  | (78) |
| print_flows | 72 | output |  | none | desc+inv |  |  | (72) |
| obs_filerecord | 59 | output | binding | none | desc | Observations only produce output. [observations] in dev3 already declares the binding parameter on the target. |  | (59) |
| export_array_ascii | 37 | output |  | none | desc+inv |  |  | (37) |
| export_array_netcdf | 24 | output |  | none | desc+inv |  |  | (24) |
| budget_filerecord | 23 | output |  | none | desc+inv |  |  | (23) |
| budgetcsv_filerecord | 23 | output |  | none | desc+inv |  |  | (23) |
| grb_filerecord | 18 | output |  | none | desc+inv |  |  | (18) |
| nogrb | 18 | output |  | none | desc+inv |  |  | (18) |
| ncf_filerecord | 8 | output | binding | none | desc | NCF is mostly NetCDF output config (chunking, deflate); its WKT is logical metadata and duplicates DIS CRS. |  | gwe-dis gwe-disv gwf-dis gwf-disv gwt-dis gwt-disv prt-dis prt-disv |
| list | 7 | output |  | none | desc+inv |  |  | chf-nam gwe-nam gwf-nam gwt-nam olf-nam prt-nam swf-nam |
| concentration_filerecord | 5 | output |  | none | desc+inv |  |  | gwt-lkt gwt-mwt gwt-oc gwt-sft gwt-uzt |
| stage_filerecord | 5 | output |  | none | desc+inv |  |  | chf-oc gwf-lak gwf-sfr olf-oc swf-oc |
| temperature_filerecord | 5 | output |  | none | desc+inv |  |  | gwe-lke gwe-mwe gwe-oc gwe-sfe gwe-uze |
| package_convergence_filerecord | 4 | output |  | none | desc+inv |  |  | gwf-csub gwf-lak gwf-sfr gwf-uzf |
| print_concentration | 4 | output |  | none | desc+inv |  |  | gwt-lkt gwt-mwt gwt-sft gwt-uzt |
| print_temperature | 4 | output |  | none | desc+inv |  |  | gwe-lke gwe-mwe gwe-sfe gwe-uze |
| nc_mesh2d_filerecord | 3 | output |  | none | desc+inv |  |  | gwe-nam gwf-nam gwt-nam |
| nc_structured_filerecord | 3 | output |  | none | desc+inv |  |  | gwe-nam gwf-nam gwt-nam |
| qoutflow_filerecord | 3 | output |  | none | desc+inv |  |  | chf-oc olf-oc swf-oc |
| qoutflowprintrecord | 3 | output |  | none | desc+inv |  |  | chf-oc olf-oc swf-oc |
| save_velocity | 3 | output |  | none | desc+inv |  |  | chf-dfw olf-dfw swf-dfw |
| vertical_offset_tolerance | 3 | output |  | none | desc+src:Disu.f90:477 | Run directive: input validation. Changes whether the run errors, not what it computes. |  | gwe-disu gwf-disu gwt-disu |
| afrcsv_filerecord | 2 | output |  | none | desc+inv |  |  | gwf-wel gwf-welg |
| csv_inner_output_filerecord | 2 | output |  | none | desc+inv |  |  | sln-ims sln-pts |
| csv_outer_output_filerecord | 2 | output |  | none | desc+inv |  |  | sln-ims sln-pts |
| csv_output_filerecord | 2 | output |  | none | desc+inv |  |  | sln-ims sln-pts |
| head_filerecord | 2 | output |  | none | desc+inv |  |  | gwf-maw gwf-oc |
| print_option | 2 | output |  | none | desc+inv |  |  | sln-ims sln-pts |
| print_stage | 2 | output |  | none | desc+inv |  |  | gwf-lak gwf-sfr |
| sorbate_filerecord | 2 | output |  | none | desc+inv |  |  | gwt-ist gwt-mst |
| track_filerecord | 2 | output |  | none | desc+inv |  |  | prt-oc prt-prp |
| trackcsv_filerecord | 2 | output |  | none | desc+inv |  |  | prt-oc prt-prp |
| chunk_face | 1 | output |  | none | desc+inv |  |  | utl-ncf |
| chunk_time | 1 | output |  | none | desc+inv |  |  | utl-ncf |
| chunk_x | 1 | output |  | none | desc+inv |  |  | utl-ncf |
| chunk_y | 1 | output |  | none | desc+inv |  |  | utl-ncf |
| chunk_z | 1 | output |  | none | desc+inv |  |  | utl-ncf |
| cim_filerecord | 1 | output |  | none | desc+inv |  |  | gwt-ist |
| cimprintrecord | 1 | output |  | none | desc+inv |  |  | gwt-ist |
| compaction_coarse_filerecord | 1 | output |  | none | desc+inv |  |  | gwf-csub |
| compaction_elastic_filerecord | 1 | output |  | none | desc+inv |  |  | gwf-csub |
| compaction_filerecord | 1 | output |  | none | desc+inv |  |  | gwf-csub |
| compaction_inelastic_filerecord | 1 | output |  | none | desc+inv |  |  | gwf-csub |
| compaction_interbed_filerecord | 1 | output |  | none | desc+inv |  |  | gwf-csub |
| concentrationprintrecord | 1 | output |  | none | desc+inv |  |  | gwt-oc |
| continue | 1 | output |  | none | desc | Run directive: policy on non-convergence. Closest to logical of the run directives. |  | sim-nam |
| coordinate_check_method | 1 | output |  | none | desc+src:Disu.f90:477 | Run directive: input validation. Changes whether the run errors, not what it computes. |  | prt-prp |
| deflate | 1 | output |  | none | desc+inv |  |  | utl-ncf |
| density_filerecord | 1 | output |  | none | desc+inv |  |  | gwf-buy |
| dev_dump_event_trace | 1 | output |  | none | desc | Run directive: logging/profiling, not a file of results. |  | prt-oc |
| dev_log_mpi | 1 | output |  | none | desc | Run directive: logging/profiling, not a file of results. |  | utl-hpc |
| digits | 1 | output |  | none | desc+inv |  |  | utl-obs |
| headprintrecord | 1 | output |  | none | desc+inv |  |  | gwf-oc |
| hpc_filerecord | 1 | output | binding | none | desc | Run directive: parallel partitioning. Results invariant up to round-off. |  | sim-nam |
| maxerrors | 1 | output |  | none | desc+src:Disu.f90:477 | Run directive: input validation. Changes whether the run errors, not what it computes. |  | sim-nam |
| memory_print_option | 1 | output |  | none | desc | Run directive: logging/profiling, not a file of results. |  | sim-nam |
| mfrcsv_filerecord | 1 | output |  | none | desc+inv |  |  | gwf-maw |
| modflow6_attr_off | 1 | output |  | none | desc+inv |  |  | utl-ncf |
| nocheck | 1 | output |  | none | desc+src:Disu.f90:477 | Run directive: input validation. Changes whether the run errors, not what it computes. |  | sim-nam |
| print_head | 1 | output |  | none | desc+inv |  |  | gwf-maw |
| print_table | 1 | output |  | none | desc | Run directive: logging/profiling, not a file of results. |  | utl-hpc |
| profile_option | 1 | output |  | none | desc | Run directive: logging/profiling, not a file of results. |  | sim-nam |
| save_saturation | 1 | output |  | none | desc+inv |  |  | gwf-npf |
| save_specific_discharge | 1 | output |  | none | mem+desc | Also forces spdis to be computed; computing it does not change the solution. |  | gwf-npf |
| shuffle | 1 | output |  | none | desc+inv |  |  | utl-ncf |
| straincg_filerecord | 1 | output |  | none | desc+inv |  |  | gwf-csub |
| strainib_filerecord | 1 | output |  | none | desc+inv |  |  | gwf-csub |
| temperatureprintrecord | 1 | output |  | none | desc+inv |  |  | gwe-oc |
| track_dropped | 1 | output |  | none | desc+inv |  |  | prt-oc |
| track_exit | 1 | output |  | none | desc+inv |  |  | prt-oc |
| track_release | 1 | output |  | none | desc+inv |  |  | prt-oc |
| track_subfeature_exit | 1 | output |  | none | desc+inv |  |  | prt-oc |
| track_terminate | 1 | output |  | none | desc+inv |  |  | prt-oc |
| track_timesrecord | 1 | output |  | none | desc | Values of an output directive. |  | prt-oc |
| track_timestep | 1 | output |  | none | desc+inv |  |  | prt-oc |
| track_usertime | 1 | output |  | none | desc+inv |  |  | prt-oc |
| track_weaksink | 1 | output |  | none | desc+inv |  |  | prt-oc |
| viscosity_filerecord | 1 | output |  | none | desc+inv |  |  | gwf-vsc |
| wc_filerecord | 1 | output |  | none | desc+inv |  |  | gwf-uzf |
| zdisplacement_filerecord | 1 | output |  | none | desc+inv |  |  | gwf-csub |
| auxiliary | 51 | logical | schema | none | desc | ADD COLUMN. |  | (51) |
| boundnames | 48 | logical | schema | none | desc | Non-unique group label; OBS can select by it. |  | (48) |
| ts_filerecord | 42 | logical | binding | dynamic | desc | Not layout: TS/TAS interpolate within a period, which period data cannot express without changing TDIS. | values interpolated from series each time step | (42) |
| auxmultname | 31 | logical | schema | dynamic | src:gwf-wel.f90:766,gwf-rch.f90:271,gwf-chd.f90:427 | Was the closest call (layout). Relabelled by the derivation axis: bound = value × aux is evaluated at every use against the current aux value, which may be a TS, so the rule itself is model content (dynamic derivation). Same structure as AUXDEPTHNAME. Snapshot re-encoding (multiply in) is still possible but loses the rule. | value × aux at every use (wel:766, rch:271, chd:427); aux may be a TS | (31) |
| angrot | 18 | logical |  | none | desc | Descriptive metadata: no runtime effect, kept by any conversion. |  | (18) |
| crs | 18 | logical |  | none | desc | Descriptive metadata: no runtime effect, kept by any conversion. |  | (18) |
| length_units | 18 | logical |  | none | desc | Descriptive metadata: no runtime effect, kept by any conversion. |  | (18) |
| xorigin | 18 | logical |  | none | desc | Descriptive metadata: no runtime effect, kept by any conversion. |  | (18) |
| yorigin | 18 | logical |  | none | desc | Descriptive metadata: no runtime effect, kept by any conversion. |  | (18) |
| mover | 14 | logical | binding | none | desc | Target-side declaration that the package takes part in an MVR relation. |  | (14) |
| flow_package_auxiliary_name | 8 | logical | binding schema | none | desc | References a column of another package's table. |  | gwe-lke gwe-mwe gwe-sfe gwe-uze gwt-lkt gwt-mwt gwt-sft gwt-uzt |
| flow_package_name | 8 | logical | binding | none | desc |  |  | gwe-lke gwe-mwe gwe-sfe gwe-uze gwt-lkt gwt-mwt gwt-sft gwt-uzt |
| fixed_cell | 4 | logical |  | none | desc | Model or numerics setting. |  | gwf-evt gwf-evta gwf-rch gwf-rcha |
| newtonoptions | 4 | logical |  | none | desc | Model or numerics setting. |  | chf-nam gwf-nam olf-nam swf-nam |
| central_in_space | 3 | logical |  | none | mem+desc | Model or numerics setting. |  | chf-dfw olf-dfw swf-dfw |
| dev_interfacemodel_on | 3 | logical |  | none | mem+desc | Model or numerics setting. |  | exg-gwegwe exg-gwfgwf exg-gwtgwt |
| dev_no_newton | 3 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-chd gwf-chdg gwf-npf |
| dev_swr_conductance | 3 | logical |  | none | mem+desc | Model or numerics setting. |  | chf-dfw olf-dfw swf-dfw |
| tas_filerecord | 3 | logical | binding | dynamic | desc | Not layout: TS/TAS interpolate within a period, which period data cannot express without changing TDIS. | arrays interpolated from series each time step | gwf-evta gwf-rcha utl-spca |
| adv_scheme | 2 | logical |  | none | desc | Model or numerics setting. |  | exg-gwegwe exg-gwtgwt |
| ats_outer_maximum_fraction | 2 | logical |  | none | desc | Model or numerics setting. |  | sln-ims sln-pts |
| ats_percel | 2 | logical |  | none | desc | Model or numerics setting. |  | gwe-adv gwt-adv |
| auto_flow_reduce | 2 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-wel gwf-welg |
| auxdepthname | 2 | logical | schema | dynamic | desc | Unlike AUXMULTNAME, gives an aux column a new physical role (drain scaling depth). | depth-scaled conductance from aux in drn_cf/drn_fc each iteration | gwf-drn gwf-drng |
| cvoptions | 2 | logical |  | none | mem+desc | Model or numerics setting. |  | exg-gwfgwf gwf-npf |
| dependent_variable_scaling | 2 | logical |  | none | mem+desc | Numerics; effect on results is round-off only. Borderline with run directive. |  | gwe-nam gwt-nam |
| dev_cubic_scaling | 2 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-drn gwf-drng |
| first_order_decay | 2 | logical | schema | none | mem+desc | Process switch that also decides which griddata arrays exist. |  | gwt-ist gwt-mst |
| fixed_conductance | 2 | logical |  | none | src:exg-swfgwf.f90:539 | Switches off depth smoothing and wetted-perimeter area: different physics, not a re-encoding. |  | exg-chfgwf exg-olfgwf |
| flow_imbalance_correction | 2 | logical |  | none | mem+desc | Model or numerics setting. |  | gwe-fmi gwt-fmi |
| gwfmodelname1 | 2 | logical | binding | none | desc |  |  | exg-gwegwe exg-gwtgwt |
| gwfmodelname2 | 2 | logical | binding | none | desc |  |  | exg-gwegwe exg-gwtgwt |
| maximum_iterations | 2 | logical |  | none | desc | Model or numerics setting. |  | gwf-lak gwf-sfr |
| no_ptcrecord | 2 | logical |  | none | desc | Model or numerics setting. |  | sln-ims sln-pts |
| scheme | 2 | logical |  | none | desc | Model or numerics setting. |  | gwe-adv gwt-adv |
| sorption | 2 | logical | schema | none | mem+desc | Process switch that also decides which griddata arrays exist. |  | gwt-ist gwt-mst |
| xt3d_off | 2 | logical |  | none | desc | Model or numerics setting. |  | gwe-cnd gwt-dsp |
| xt3d_rhs | 2 | logical |  | none | desc | Model or numerics setting. |  | gwe-cnd gwt-dsp |
| zero_order_decay | 2 | logical | schema | none | mem+desc | Process switch that also decides which griddata arrays exist. |  | gwt-ist gwt-mst |
| alternative_cell_averaging | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-npf |
| ats_filerecord | 1 | logical | binding | none | desc |  |  | sim-tdis |
| beta | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-csub |
| cell_averaging | 1 | logical |  | none | desc | Model or numerics setting. |  | exg-gwfgwf |
| cnd_xt3d_off | 1 | logical |  | none | desc | Model or numerics setting. |  | exg-gwegwe |
| cnd_xt3d_rhs | 1 | logical |  | none | desc | Model or numerics setting. |  | exg-gwegwe |
| denseref | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-buy |
| density_water | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwe-est |
| dev_cycle_detection_window | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | prt-prp |
| dev_efh_formulation | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-buy |
| dev_exit_solve_method | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | prt-prp |
| dev_forceternary | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | prt-prp |
| dev_oldstorageformulation | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-sto |
| dev_omega | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-npf |
| dev_original_specific_storage | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-sto |
| dev_storage_weight | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-sfr |
| disable_storage_change_integration | 1 | logical |  | none | desc | Model or numerics setting. |  | utl-tvs |
| drape | 1 | logical |  | none | desc | Model or numerics setting. |  | prt-prp |
| dry_tracking_method | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | prt-prp |
| dsp_xt3d_off | 1 | logical |  | none | desc | Model or numerics setting. |  | exg-gwtgwt |
| dsp_xt3d_rhs | 1 | logical |  | none | desc | Model or numerics setting. |  | exg-gwtgwt |
| effective_stress_lag | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-csub |
| exit_solve_tolerance | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | prt-prp |
| explicit | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-gnc |
| extend_tracking | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | prt-prp |
| flow_correction | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-maw |
| flowing_wells | 1 | logical |  | none | desc |  |  | gwf-maw |
| gammaw | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-csub |
| gnc_filerecord | 1 | logical | binding | none | desc |  |  | exg-gwfgwf |
| heat_capacity_water | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwe-est |
| hhformulation_rhs | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-buy |
| highest_cell_saturation | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-npf |
| highest_saturated | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwt-src |
| istopzone | 1 | logical |  | none | desc | Model or numerics setting. |  | prt-prp |
| latent_heat_vaporization | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwe-est |
| linear_gwet | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-uzf |
| local_z | 1 | logical |  | dynamic | src:prt-prp.f90:706 | Looks like a coordinate encoding, but scales by simulated saturation at release time (gwfsat), so it is a statement about the model, not a static lens. | scaled by simulated saturation at release (prt-prp:706) | prt-prp |
| maximum_depth_change | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-sfr |
| maximum_picard_iterations | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-sfr |
| maximum_stage_change | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-lak |
| mve_filerecord | 1 | logical | binding | none | desc |  |  | exg-gwegwe |
| mvr_filerecord | 1 | logical | binding | none | desc |  |  | exg-gwfgwf |
| mvt_filerecord | 1 | logical | binding | none | desc |  |  | exg-gwtgwt |
| ndelaycells | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-csub |
| newton | 1 | logical |  | none | desc | Model or numerics setting. |  | exg-gwfgwf |
| no_well_storage | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-maw |
| perched | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-npf |
| release_time_frequency | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | prt-prp |
| release_time_tolerance | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | prt-prp |
| release_timesrecord | 1 | logical |  | none | desc | Values. Has an alternative encoding (RELEASETIMES block / file) to check in step 2. |  | prt-prp |
| rewet_record | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-npf |
| shutdown_kappa | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-maw |
| shutdown_theta | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-maw |
| simulate_et | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-uzf |
| simulate_gwseep | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-uzf |
| square_gwet | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-uzf |
| ss_confined_only | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-sto |
| start_date_time | 1 | logical |  | none | desc | Descriptive metadata: no runtime effect, kept by any conversion. |  | sim-tdis |
| stop_at_weak_sink | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | prt-prp |
| stoptime | 1 | logical |  | none | desc | Model or numerics setting. |  | prt-prp |
| stoptraveltime | 1 | logical |  | none | desc | Model or numerics setting. |  | prt-prp |
| storage | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-sfr |
| surf_rate_specified | 1 | logical | schema | none | mem+desc | Adds PETM0 column. |  | gwf-evt |
| surfdep | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-lak |
| temperature_species_name | 1 | logical | schema | none | mem+desc | Key reference to a PACKAGEDATA row (intra-component reference). |  | gwf-vsc |
| thermal_a2 | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-vsc |
| thermal_a3 | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-vsc |
| thermal_a4 | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-vsc |
| thermal_formulation | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-vsc |
| thickstrt | 1 | logical |  | static | desc | Thickness from STRT-BOT: not re-encodable by editing TOP, which has other uses. | thickness from STRT - BOT, computed once; no input column holds the result, so it stays logical | gwf-npf |
| time_units | 1 | logical |  | none | desc | Descriptive metadata: no runtime effect, kept by any conversion. |  | sim-tdis |
| tvk_filerecord | 1 | logical | binding | none | desc |  |  | gwf-npf |
| tvs_filerecord | 1 | logical | binding | none | desc |  |  | gwf-sto |
| unsat_etae | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-uzf |
| unsat_etwc | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-uzf |
| update_material_properties | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-csub |
| viscref | 1 | logical |  | none | desc | Model or numerics setting. |  | gwf-vsc |
| wkt | 1 | logical |  | none | desc | Descriptive metadata: no runtime effect, kept by any conversion. |  | utl-ncf |
| xt3d | 1 | logical |  | none | desc | Model or numerics setting. |  | exg-gwfgwf |
| xt3doptions | 1 | logical |  | none | mem+desc | Model or numerics setting. |  | gwf-npf |
| zero_order_decay_solid | 1 | logical | schema | none | mem+desc | Process switch that also decides which griddata arrays exist. |  | gwe-est |
| zero_order_decay_water | 1 | logical | schema | none | mem+desc | Process switch that also decides which griddata arrays exist. |  | gwe-est |
