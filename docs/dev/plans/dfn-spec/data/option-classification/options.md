# Options inventory (dev3)

146 components, 1035 option fields, 224 distinct names.

| name | count | form | files | memory | memory_coverage | description |
|---|---|---|---|---|---|---|
| save_flows | 79 | keyword |  | ipakcb(set_in=ar) iprpak(set_in=ar) | 51/79 | keyword to indicate that all model package flow terms will be written to the file specified with 'BUDGET FILEOUT' in Output Control. |
| print_input | 78 | keyword |  | ipr_input(set_in=ar) iprflow(set_in=ar) iprpak(set_in=ar) | 43/78 | keyword to indicate that the list of all model stress package information will be written to the listing file immediately after it is read. |
| print_flows | 72 | keyword |  | ipr_flow(set_in=ar) iprflow(set_in=ar) | 41/72 | keyword to indicate that the list of all model package flow rates will be printed to the listing file for every stress period time step in which 'BUDGET PRINT' is specified in Output Control. |
| obs_filerecord | 59 | record | in:utl-obs |  |  | is the file name of the observations input file for this exchange. |
| auxiliary | 51 | value |  |  |  | defines an array of one or more auxiliary variable names. |
| boundnames | 48 | keyword |  |  |  | keyword to indicate that boundary names may be provided with the list of constant-head cells. |
| ts_filerecord | 42 | record | in:utl-ts |  |  | defines a time-series file defining time series that can be used to assign time-varying values. |
| export_array_ascii | 37 | keyword |  | export_ascii(set_in=ar) | 37/37 | keyword that specifies input griddata arrays should be written to layered ascii output files. |
| auxmultname | 31 | value |  |  |  | name of auxiliary variable to be used as multiplier of CHD head value. |
| export_array_netcdf | 24 | keyword |  | export_nc(set_in=ar) | 24/24 | keyword that specifies input gridded arrays should be written to the model output NetCDF file with attributes that support using the generated file as a MODFLOW 6 simulation input. |
| budget_filerecord | 23 | record | out:? |  |  | name of the binary output file to write budget information. |
| budgetcsv_filerecord | 23 | record | out:? |  |  | name of the comma-separated value (CSV) output file to write budget summary information. |
| angrot | 18 | value |  |  |  | counter-clockwise rotation angle (in degrees) of the model grid coordinate system relative to a real-world coordinate system. |
| crs | 18 | value |  |  |  | is a real-world coordinate reference system (CRS) for the model, for example, an EPSG integer code (e.g. |
| grb_filerecord | 18 | record | out:? |  |  | defines a binary grid output file. |
| length_units | 18 | value |  |  |  | is the length units used for this model. |
| nogrb | 18 | keyword |  |  |  | keyword to deactivate writing of the binary grid file. |
| xorigin | 18 | value |  |  |  | x-position of the origin used for model grid vertices. |
| yorigin | 18 | value |  |  |  | y-position of the origin used for model grid vertices. |
| mover | 14 | keyword |  |  |  | keyword to indicate that this instance of the api boundary Package can be used with the Water Mover (MVR) Package. |
| flow_package_auxiliary_name | 8 | value |  |  |  | keyword to specify the name of an auxiliary variable in the corresponding flow package. |
| flow_package_name | 8 | value |  |  |  | keyword to specify the name of the corresponding flow package. |
| ncf_filerecord | 8 | record | in:utl-ncf |  |  | defines a NetCDF configuration (NCF) input file. |
| list | 7 | value |  |  |  | is name of the listing file to create for this CHF model. |
| concentration_filerecord | 5 | record | out:? | concfile(set_in=ar) | 1/5 | name of the binary output file to write concentration information. |
| length_conversion | 5 | value |  | lengthconv(set_in=ar) | 3/5 | real value that is used to convert user-specified Manning's roughness coefficients from meters to model length units. |
| readarraygrid | 5 | keyword |  |  |  | indicates that array-based grid input will be used for the constant head package. |
| stage_filerecord | 5 | record | out:? |  |  | name of the output file to write stage information. |
| temperature_filerecord | 5 | record | out:? | tempfile(set_in=ar) | 1/5 | name of the binary output file to write temperature information. |
| time_conversion | 5 | value |  | timeconv(set_in=ar) | 3/5 | real value that is used to convert user-specified Manning's roughness coefficients from seconds to model time units. |
| fixed_cell | 4 | keyword |  |  |  | indicates that evapotranspiration will not be reassigned to a cell underlying the cell specified in the list if the specified cell is inactive. |
| newtonoptions | 4 | record |  |  |  | none |
| package_convergence_filerecord | 4 | record | out:? | pkgconverge(set_in=ar) pkgconvergefn(set_in=ar) | 1/4 | name of the comma spaced values output file to write package convergence information. |
| print_concentration | 4 | keyword |  |  |  | keyword to indicate that the list of lake {#2} will be printed to the listing file for every stress period in which 'CONCENTRATION PRINT' is specified in Output Control. |
| print_temperature | 4 | keyword |  |  |  | keyword to indicate that the list of lake {#2} will be printed to the listing file for every stress period in which 'TEMPERATURE PRINT' is specified in Output Control. |
| central_in_space | 3 | keyword |  | icentral(set_in=ar) | 3/3 | keyword to indicate conductance should be calculated using central-in-space weighting instead of the default upstream weighting approach. |
| dev_interfacemodel_on | 3 | keyword |  | dev_ifmod_on(set_in=ar) | 3/3 | activates the interface model mechanism for calculating the coefficients at (and possibly near) the exchange. |
| dev_no_newton | 3 | keyword |  | inewton(set_in=ar) | 3/3 | turn off Newton for unconfined cells |
| dev_swr_conductance | 3 | keyword |  | iswrcond(set_in=ar) | 3/3 | use the conductance formulation in the Surface Water Routing (SWR) Process for MODFLOW-2005. |
| nc_filerecord | 3 | record | in:? | netcdf_fname(set_in=ar) | 3/3 | NetCDF filerecord |
| nc_mesh2d_filerecord | 3 | record | out:? |  |  | NetCDF layered mesh fileout record. |
| nc_structured_filerecord | 3 | record | out:? | netcdf_struct(set_in=ar) | 3/3 | NetCDF structured fileout record. |
| qoutflow_filerecord | 3 | record | out:? |  |  | name of the output file to write conc information. |
| qoutflowprintrecord | 3 | record |  |  |  |  |
| readasarrays | 3 | keyword |  |  |  | indicates that array-based input will be used for the Evapotranspiration Package. |
| save_velocity | 3 | keyword |  | isavvelocity(set_in=ar) | 3/3 | keyword to indicate that x, y, and z components of velocity will be calculated at cell centers and written to the budget file, which is specified with 'BUDGET SAVE FILE' in Output Control. |
| tas_filerecord | 3 | record | in:utl-tas |  |  | defines a time-array-series file defining a time-array series that can be used to assign time-varying values. |
| vertical_offset_tolerance | 3 | value |  | voffsettol(set_in=ar) | 3/3 | checks are performed to ensure that the top of a cell is not higher than the bottom of an overlying cell. |
| adv_scheme | 2 | value |  |  |  | scheme used to solve the advection term. |
| afrcsv_filerecord | 2 | record | out:? | afrcsv(set_in=ar) | 2/2 | name of the comma-separated value (CSV) output file to write information about well extraction rates that have been reduced by the program. |
| ats_outer_maximum_fraction | 2 | value |  |  |  | real value defining the fraction of the maximum allowable outer iterations used with the Adaptive Time Step (ATS) capability if it is active. |
| ats_percel | 2 | value |  |  |  | fractional cell distance submitted by the ADV Package to the adaptive time stepping (ATS) package. |
| auto_flow_reduce | 2 | value |  | flowred(set_in=ar) | 2/2 | keyword and real value that defines the fraction of the cell thickness used as an interval for smoothly adjusting negative pumping rates to 0 in cells with head values less than or equal to the bottom |
| auxdepthname | 2 | value |  |  |  | name of a variable listed in AUXILIARY that defines the depth at which drainage discharge will be scaled. |
| complexity | 2 | value |  |  |  | is an optional keyword that defines default non-linear and linear solver parameters. |
| csv_inner_output_filerecord | 2 | record | out:? |  |  | name of the ascii comma separated values output file to write solver convergence information. |
| csv_outer_output_filerecord | 2 | record | out:? |  |  | name of the ascii comma separated values output file to write maximum dependent-variable (for example, head) change convergence information at the end of each outer iteration for each time step. |
| csv_output_filerecord | 2 | record | out:? |  |  | name of the ascii comma separated values output file to write solver convergence information. |
| cvoptions | 2 | record |  | idewatcv(set_in=ar) ivarcv(set_in=ar) | 1/2 | none |
| dependent_variable_scaling | 2 | keyword |  | idv_scale(set_in=ar) | 2/2 | flag to scale X and RHS to avoid very large positive or negative dependent variable values |
| dev_cubic_scaling | 2 | keyword |  | icubicsfac(set_in=ar) | 2/2 | cubic-scaling is used to scale the drain conductance |
| first_order_decay | 2 | keyword |  | order1_decay(set_in=ar) | 2/2 | is a text keyword to indicate that first-order decay will occur. |
| fixed_conductance | 2 | keyword |  | ifixedcond(set_in=ar) | 2/2 | keyword to indicate that the product of the bedleak and cfact input variables in the exchangedata block represents conductance. |
| flow_imbalance_correction | 2 | keyword |  | imbalancecorrect(set_in=ar) | 2/2 | correct for an imbalance in flows by assuming that any residual flow error comes in or leaves at the temperature of the cell. |
| flow_reduction_length | 2 | keyword |  | iflowredlen(set_in=ar) | 2/2 | keyword that indicates the AUTO_FLOW_REDUCE value is a length instead of a fraction of the cell thickness. |
| gwfmodelname1 | 2 | value |  |  |  | keyword to specify name of first corresponding GWF Model. |
| gwfmodelname2 | 2 | value |  |  |  | keyword to specify name of second corresponding GWF Model. |
| head_filerecord | 2 | record | out:? |  |  | name of the binary output file to write head information. |
| maximum_iterations | 2 | value |  |  |  | integer value that defines the maximum number of Newton-Raphson iterations allowed for a lake. |
| no_ptcrecord | 2 | record |  |  |  | is an optional keyword that is used to define options for disabling pseudo-transient continuation (PTC). |
| print_option | 2 | value |  |  |  | is a flag that controls printing of convergence information from the solver. |
| print_stage | 2 | keyword |  |  |  | keyword to indicate that the list of lake {#2} will be printed to the listing file for every stress period in which 'HEAD PRINT' is specified in Output Control. |
| scheme | 2 | value |  |  |  | scheme used to solve the advection term. |
| sorbate_filerecord | 2 | record | out:? |  |  | name of the output file to write immobile sorbate concentration information. |
| sorption | 2 | value |  |  |  | is a text keyword to indicate that sorption will be activated. |
| track_filerecord | 2 | record | out:? |  |  | name of the binary output file to write tracking information. |
| trackcsv_filerecord | 2 | record | out:? |  |  | name of the comma-separated value (CSV) file to write tracking information. |
| xt3d_off | 2 | keyword |  |  |  | deactivate the xt3d method and use the faster and less accurate approximation. |
| xt3d_rhs | 2 | keyword |  |  |  | add xt3d terms to right-hand side, when possible. |
| zero_order_decay | 2 | keyword |  | order0_decay(set_in=ar) | 2/2 | is a text keyword to indicate that zero-order decay will occur. |
| alternative_cell_averaging | 1 | value |  | cellavg(set_in=ar) | 1/1 | is a text keyword to indicate that an alternative method will be used for calculating the conductance for horizontal cell connections. |
| ats_filerecord | 1 | record | in:utl-ats |  |  | defines an adaptive time step (ATS) input file defining ATS controls. |
| beta | 1 | value |  |  |  | compressibility of water. |
| cell_averaging | 1 | value |  |  |  | is a keyword and text keyword to indicate the method that will be used for calculating the conductance for horizontal cell connections. |
| cell_fraction | 1 | keyword |  |  |  | keyword to indicate that the thickness of interbeds will be specified in terms of the fraction of cell thickness. |
| chunk_face | 1 | value |  |  |  | is the keyword used to provide a data chunk size for the face dimension in a NETCDF_MESH2D output file. |
| chunk_time | 1 | value |  |  |  | is the keyword used to provide a data chunk size for the time dimension in a NETCDF_MESH2D or NETCDF_STRUCTURED output file. |
| chunk_x | 1 | value |  |  |  | is the keyword used to provide a data chunk size for the x dimension in a NETCDF_STRUCTURED output file. |
| chunk_y | 1 | value |  |  |  | is the keyword used to provide a data chunk size for the y dimension in a NETCDF_STRUCTURED output file. |
| chunk_z | 1 | value |  |  |  | is the keyword used to provide a data chunk size for the z dimension in a NETCDF_STRUCTURED output file. |
| cim_filerecord | 1 | record | out:? | cim(set_in=ar) cimopt(set_in=ar) | 1/1 | name of the output file to write immobile concentrations. |
| cimprintrecord | 1 | record |  | cim(set_in=ar) cimopt(set_in=ar) | 1/1 |  |
| cnd_xt3d_off | 1 | keyword |  |  |  | deactivate the xt3d method for the dispersive flux and use the faster and less accurate approximation for this exchange. |
| cnd_xt3d_rhs | 1 | keyword |  |  |  | add xt3d dispersion terms to right-hand side, when possible, for this exchange. |
| compaction_coarse_filerecord | 1 | record | out:? | cmpcoarse(set_in=ar) cmpcoarsefn(set_in=ar) | 1/1 | name of the binary output file to write elastic coarse-grained material compaction information. |
| compaction_elastic_filerecord | 1 | record | out:? | cmpelastic(set_in=ar) elasticcmpfn(set_in=ar) | 1/1 | name of the binary output file to write elastic interbed compaction information. |
| compaction_filerecord | 1 | record | out:? | cmpfn(set_in=ar) | 1/1 | name of the binary output file to write compaction information. |
| compaction_inelastic_filerecord | 1 | record | out:? | cmpinelastic(set_in=ar) inelasticcmpfn(set_in=ar) | 1/1 | name of the binary output file to write inelastic interbed compaction information. |
| compaction_interbed_filerecord | 1 | record | out:? | cmpinterbed(set_in=ar) interbedcmpfn(set_in=ar) | 1/1 | name of the binary output file to write interbed compaction information. |
| compression_indices | 1 | keyword |  | icompress(set_in=ar) | 1/1 | keyword to indicate that the recompression (CR) and compression (CC) indices are specified instead of the elastic specific storage (SSE) and inelastic specific storage (SSV) coefficients. |
| concentrationprintrecord | 1 | record |  |  |  |  |
| continue | 1 | keyword |  |  |  | keyword flag to indicate that the simulation should continue even if one or more solutions do not converge. |
| coordinate_check_method | 1 | value |  | ichkmeth(set_in=ar) | 1/1 | approach for verifying that release point coordinates are in the cell with the specified ID. |
| deflate | 1 | value |  |  |  | is the variable deflate level (0=min, 9=max) in the NetCDF file. |
| denseref | 1 | value |  |  |  | fluid reference density used in the equation of state. |
| density_filerecord | 1 | record | out:? |  |  | name of the binary output file to write density information. |
| density_water | 1 | value |  | rhow(set_in=ar) | 1/1 | density of water used by calculations related to heat storage and conduction. |
| dev_cycle_detection_window | 1 | value |  | icycwin(set_in=ar) | 1/1 | integer value defining the size of the window (number of consecutive exit events) used for cycle detection. |
| dev_dump_event_trace | 1 | keyword |  | dev_dump_evtrace(set_in=ar) | 1/1 | print a verbose particle tracking event trace to standard output |
| dev_efh_formulation | 1 | keyword |  | dev_efh_form(set_in=ar) | 1/1 | use the variable-density equivalent freshwater head formulation instead of the hydraulic head head formulation. |
| dev_exit_solve_method | 1 | value |  | iexmeth(set_in=ar) | 1/1 | the method for iterative solution of particle exit location and time in the generalized Pollock's method. |
| dev_forceternary | 1 | keyword |  | frctrn(set_in=ar) | 1/1 | force use of the ternary tracking method regardless of cell type in DISV grids. |
| dev_log_mpi | 1 | keyword |  |  |  | keyword to enable (extremely verbose) logging of mpi traffic to file. |
| dev_oldstorageformulation | 1 | keyword |  | iconf_ss(set_in=ar) | 1/1 | development option flag for old storage formulation |
| dev_omega | 1 | value |  | satomega(set_in=ar) | 1/1 | set saturation omega value |
| dev_original_specific_storage | 1 | keyword |  | iorig_ss(set_in=ar) | 1/1 | flag indicating the original storage specific storage formulation should be used |
| dev_storage_weight | 1 | value |  |  |  | real number value that defines the time weighting factor used to calculate the change in channel storage. |
| digits | 1 | value |  |  |  | Keyword and an integer digits specifier used for conversion of simulated values to text on output. |
| disable_storage_change_integration | 1 | keyword |  |  |  | keyword that deactivates inclusion of storage derivative terms in the STO package matrix formulation. |
| drape | 1 | keyword |  |  |  | is a text keyword to indicate that if a particle's release point is in a cell that happens to be inactive at release time, the particle is to be moved to the topmost active cell below it, if any. |
| dry_tracking_method | 1 | value |  | idrymeth(set_in=ar) | 1/1 | is a string indicating how particles should behave in dry-but-active cells (as can occur with the Newton formulation). |
| dsp_xt3d_off | 1 | keyword |  |  |  | deactivate the xt3d method for the dispersive flux and use the faster and less accurate approximation for this exchange. |
| dsp_xt3d_rhs | 1 | keyword |  |  |  | add xt3d dispersion terms to right-hand side, when possible, for this exchange. |
| effective_stress_lag | 1 | keyword |  | stress_lag(set_in=ar) | 1/1 | keyword to indicate the effective stress from the previous time step will be used to calculate specific storage values. |
| exit_solve_tolerance | 1 | value |  | extol(set_in=ar) | 1/1 | the convergence tolerance for iterative solution of particle exit location and time in the generalized Pollock's method. |
| explicit | 1 | keyword |  |  |  | keyword to indicate that the ghost node correction is applied in an explicit manner on the right-hand side of the matrix. |
| extend_tracking | 1 | keyword |  | extend(set_in=ar) | 1/1 | indicates that particles should be tracked beyond the end of the simulation's final time step (using that time step's flows) until particles terminate or reach a specified stop time. |
| flow_correction | 1 | keyword |  |  |  | keyword that activates flow corrections in cases where the head in a multi-aquifer well is below the bottom of the screen for a connection or the head in a convertible cell connected to a multi-aquife |
| flowing_wells | 1 | keyword |  |  |  | keyword that activates the flowing wells option for the multi-aquifer well package. |
| gammaw | 1 | value |  |  |  | unit weight of water. |
| gnc_filerecord | 1 | record | in:gwf-gnc |  |  | is the file name for ghost node correction input file. |
| head_based | 1 | keyword |  |  |  | keyword to indicate the head-based formulation will be used to simulate coarse-grained aquifer materials and no-delay and delay interbeds. |
| headprintrecord | 1 | record |  |  |  |  |
| heat_capacity_water | 1 | value |  | cpw(set_in=ar) | 1/1 | heat capacity of water used by calculations related to heat storage and conduction. |
| hhformulation_rhs | 1 | keyword |  | hhform_rhs(set_in=ar) | 1/1 | use the variable-density hydraulic head formulation and add off-diagonal terms to the right-hand. |
| highest_cell_saturation | 1 | keyword |  | ihighcellsat(set_in=ar) | 1/1 | keyword indicating that the maximum cell bottom will be used to calculate the saturation used to calculate the horizontal conductance between cells. |
| highest_saturated | 1 | keyword |  | highest_sat(set_in=ar) | 1/1 | Apply mass source loading rate to specified CELLID or highest underlying cell with a cell saturation greater than zero. |
| hpc_filerecord | 1 | record | in:utl-hpc |  |  | hpc record |
| initial_preconsolidation_head | 1 | keyword |  | precon_head(set_in=ar) | 1/1 | keyword to indicate that preconsolidation heads will be specified for no-delay and delay interbeds in the PACKAGEDATA block. |
| istopzone | 1 | value |  |  |  | integer value defining the stop zone number. |
| k22overk | 1 | keyword |  | ik22overk(set_in=ar) | 1/1 | keyword to indicate that specified K22 is a ratio of K22 divided by K. |
| k33overk | 1 | keyword |  | ik33overk(set_in=ar) | 1/1 | keyword to indicate that specified K33 is a ratio of K33 divided by K. |
| latent_heat_vaporization | 1 | value |  | latheatvap(set_in=ar) | 1/1 | latent heat of vaporization is the amount of energy that is required to convert a given quantity of liquid into a gas and is associated with evaporative cooling. |
| linear_gwet | 1 | keyword |  |  |  | keyword specifying that groundwater ET will be simulated using the original ET formulation of MODFLOW-2005. |
| local_z | 1 | keyword |  | localz(set_in=ar) | 1/1 | indicates that 'zrpt' defines the local z coordinate of the release point within the cell, with value of 0 at the bottom and 1 at the effective top of the cell. |
| maxerrors | 1 | value |  |  |  | maximum number of errors that will be stored and printed. |
| maximum_depth_change | 1 | value |  |  |  | real value that defines the depth closure tolerance. |
| maximum_picard_iterations | 1 | value |  |  |  | integer value that defines the maximum number of Streamflow Routing picard iterations allowed when solving for reach stages and flows as part of the GWF formulate step. |
| maximum_stage_change | 1 | value |  |  |  | real value that defines the lake stage closure tolerance. |
| memory_print_option | 1 | value |  | prmem(set_in=ar) | 1/1 | is a flag that controls printing of detailed memory manager usage to the end of the simulation list file. |
| mfrcsv_filerecord | 1 | record | out:? |  |  | name of the comma-separated value (CSV) output file to write information about multi-aquifer well extraction or injection rates that have been reduced by the program. |
| modelnames | 1 | keyword |  |  |  | keyword to indicate that all package names will be preceded by the model name for the package. |
| modflow6_attr_off | 1 | keyword |  | attr_off(set_in=ar) | 1/1 | is the keyword used to turn off internal input tagging in the model NetCDF file. |
| mve_filerecord | 1 | record | in:gwe-mve |  |  | is the file name of the transport mover input file to apply to this exchange. |
| mvr_filerecord | 1 | record | in:gwf-mvr |  |  | is the file name of the water mover input file to apply to this exchange. |
| mvt_filerecord | 1 | record | in:gwt-mvt |  |  | is the file name of the transport mover input file to apply to this exchange. |
| ndelaycells | 1 | value |  |  |  | number of nodes used to discretize delay interbeds. |
| newton | 1 | keyword |  |  |  | keyword that activates the Newton-Raphson formulation for groundwater flow between connected, convertible groundwater cells. |
| no_well_storage | 1 | keyword |  |  |  | keyword that deactivates inclusion of well storage contributions to the multi-aquifer well package continuity equation. |
| nocheck | 1 | keyword |  |  |  | keyword flag to indicate that the model input check routines should not be called prior to each time step. |
| perched | 1 | keyword |  | iperched(set_in=ar) | 1/1 | keyword to indicate that when a cell is overlying a dewatered convertible cell, the head difference used in Darcy's Law is equal to the head in the overlying cell minus the bottom elevation of the ove |
| print_head | 1 | keyword |  |  |  | keyword to indicate that the list of multi-aquifer well {#2} will be printed to the listing file for every stress period in which 'HEAD PRINT' is specified in Output Control. |
| print_table | 1 | keyword |  |  |  | keyword to indicate that the partition table will be printed to the listing file. |
| profile_option | 1 | value |  | prprof(set_in=ar) | 1/1 | is a flag that controls performance profiling and reporting. |
| release_time_frequency | 1 | value |  | rtfreq(set_in=ar) | 1/1 | real number indicating the time frequency at which to release particles. |
| release_time_tolerance | 1 | value |  | rttol(set_in=ar) | 1/1 | real number indicating the tolerance within which to consider consecutive release times coincident. |
| release_timesfilerecord | 1 | record |  | release_timesfn(set_in=ar) | 1/1 | name of the release times file. |
| release_timesrecord | 1 | record |  |  |  | times to release, relative to the beginning of the simulation. |
| rewet_record | 1 | record |  | irewet(set_in=ar) | 1/1 | is a keyword and factor that is included in the calculation of the head that is initially established at a cell when that cell is converted from dry to wet. |
| save_saturation | 1 | keyword |  | isavsat(set_in=ar) | 1/1 | keyword to indicate that cell saturation will be written to the budget file, which is specified with 'BUDGET SAVE FILE' in Output Control. |
| save_specific_discharge | 1 | keyword |  | isavspdis(set_in=ar) | 1/1 | keyword to indicate that x, y, and z components of specific discharge will be calculated at cell centers and written to the budget file, which is specified with 'BUDGET SAVE FILE' in Output Control. |
| shuffle | 1 | keyword |  |  |  | is the keyword used to turn on the NetCDF variable shuffle filter when the deflate option is also set. |
| shutdown_kappa | 1 | value |  |  |  | value that defines the weight applied to discharge rate for wells that limit the water level in a discharging well (defined using the HEAD_LIMIT keyword in the stress period data). |
| shutdown_theta | 1 | value |  |  |  | value that defines the weight applied to discharge rate for wells that limit the water level in a discharging well (defined using the HEAD_LIMIT keyword in the stress period data). |
| simulate_et | 1 | keyword |  |  |  | keyword specifying that ET in the unsaturated (UZF) and saturated zones (GWF) will be simulated. |
| simulate_gwseep | 1 | keyword |  |  |  | keyword specifying that groundwater discharge (GWSEEP) to land surface will be simulated. |
| specified_initial_delay_head | 1 | keyword |  | delay_head(set_in=ar) | 1/1 | keyword to indicate that absolute initial delay bed head will be specified for interbeds defined in the PACKAGEDATA block. |
| specified_initial_interbed_state | 1 | keyword |  | interbed_state(set_in=ar) | 1/1 | keyword to indicate that absolute preconsolidation stresses (heads) and delay bed heads will be specified for interbeds defined in the PACKAGEDATA block. |
| specified_initial_preconsolidation_stress | 1 | keyword |  | precon_stress(set_in=ar) | 1/1 | keyword to indicate that absolute preconsolidation stresses (heads) will be specified for interbeds defined in the PACKAGEDATA block. |
| square_gwet | 1 | keyword |  |  |  | keyword specifying that groundwater ET will be simulated by assuming a constant ET rate for groundwater levels between land surface (TOP) and land surface minus the ET extinction depth (TOP-EXTDP). |
| ss_confined_only | 1 | keyword |  |  |  | keyword to indicate that compressible storage is only calculated for a convertible cell (ICONVERT>0) when the cell is under confined conditions (head greater than or equal to the top of the cell). |
| start_date_time | 1 | value |  |  |  | is the starting date and time of the simulation. |
| stop_at_weak_sink | 1 | keyword |  | istopweaksink(set_in=ar) | 1/1 | is a text keyword to indicate that a particle is to terminate when it enters a cell that is a weak sink. |
| stoptime | 1 | value |  |  |  | real value defining the maximum simulation time to which particles in the package can be tracked. |
| stoptraveltime | 1 | value |  |  |  | real value defining the maximum travel time over which particles in the model can be tracked. |
| storage | 1 | keyword |  |  |  | keyword that activates storage contributions to the stream-flow routing package continuity equation. |
| storagecoefficient | 1 | keyword |  | istor_coef(set_in=ar) | 1/1 | keyword to indicate that the SS array is read as storage coefficient rather than specific storage. |
| straincg_filerecord | 1 | record | out:? | coarsestrainfn(set_in=ar) csvcoarse(set_in=ar) | 1/1 | name of the comma-separated-values output file to write final coarse-grained material strain information. |
| strainib_filerecord | 1 | record | out:? | csvinterbed(set_in=ar) interbedstrainfn(set_in=ar) | 1/1 | name of the comma-separated-values output file to write final interbed strain information. |
| surf_rate_specified | 1 | keyword |  | surfratespec(set_in=ar) | 1/1 | indicates that the proportion of the evapotranspiration rate at the ET surface will be specified as PETM0 in list input. |
| surfdep | 1 | value |  |  |  | real value that defines the surface depression depth for VERTICAL lake-GWF connections. |
| temperature_species_name | 1 | value |  | temp_specname(set_in=ar) | 1/1 | string used to identify the auxspeciesname in PACKAGEDATA that corresponds to the temperature species. |
| temperatureprintrecord | 1 | record |  |  |  |  |
| thermal_a2 | 1 | value |  |  |  | is an empirical parameter specified by the user for calculating viscosity using a nonlinear formulation. |
| thermal_a3 | 1 | value |  |  |  | is an empirical parameter specified by the user for calculating viscosity using a nonlinear formulation. |
| thermal_a4 | 1 | value |  |  |  | is an empirical parameter specified by the user for calculating viscosity using a nonlinear formulation. |
| thermal_formulation | 1 | value |  | thermal_form(set_in=ar) | 1/1 | may be used for specifying which viscosity formulation to use for the temperature species. |
| thickstrt | 1 | keyword |  | ithickstrt(set_in=ar) | 1/1 | indicates that cells having a negative ICELLTYPE are confined, and their cell thickness for conductance calculations will be computed as STRT-BOT rather than TOP-BOT. |
| time_units | 1 | value |  |  |  | is the time units of the simulation. |
| track_dropped | 1 | keyword |  |  |  | keyword to indicate that particle tracking output is to be written when a particle is dropped to the water table via DRY_TRACKING_METHOD DROP. |
| track_exit | 1 | keyword |  |  |  | keyword to indicate that particle tracking output is to be written when a particle exits a grid feature (e.g. |
| track_release | 1 | keyword |  |  |  | keyword to indicate that particle tracking output is to be written when a particle is released |
| track_subfeature_exit | 1 | keyword |  | track_subf_exit(set_in=ar) | 1/1 | keyword to indicate that particle tracking output is to be written when a particle exits a sub-grid-scale feature. |
| track_terminate | 1 | keyword |  |  |  | keyword to indicate that particle tracking output is to be written when a particle terminates for any reason |
| track_timesfilerecord | 1 | record |  |  |  | name of the tracking times file |
| track_timesrecord | 1 | record |  |  |  | times to track, relative to the beginning of the simulation. |
| track_timestep | 1 | keyword |  |  |  | keyword to indicate that particle tracking output is to be written at the end of each time step |
| track_usertime | 1 | keyword |  |  |  | keyword to indicate that particle tracking output is to be written at user-specified times, provided as double precision values in the TRACKTIMES block. |
| track_weaksink | 1 | keyword |  |  |  | keyword to indicate that particle tracking output is to be written when a particle exits a weak sink (a cell which removes some but not all inflow from adjacent cells) |
| tvk_filerecord | 1 | record | in:utl-tvk |  |  | defines a time-varying hydraulic conductivity (TVK) input file. |
| tvs_filerecord | 1 | record | in:utl-tvs |  |  | defines a time-varying storage (TVS) input file. |
| unit_conversion | 1 | value |  |  |  | real value that is used to convert user-specified Manning's roughness coefficients from seconds per meters$^{1/3}$ to model length and time units. |
| unsat_etae | 1 | keyword |  |  |  | keyword specifying that ET in the unsaturated zone will be simulated using a capillary pressure based formulation. |
| unsat_etwc | 1 | keyword |  |  |  | keyword specifying that ET in the unsaturated zone will be simulated as a function of the specified PET rate while the water content (THETA) is greater than the ET extinction water content (EXTWC). |
| update_material_properties | 1 | keyword |  | matprop(set_in=ar) | 1/1 | keyword to indicate that the thickness and void ratio of coarse-grained and interbed sediments (delay and no-delay) will vary during the simulation. |
| viscosity_filerecord | 1 | record | out:? |  |  | name of the binary output file to write viscosity information. |
| viscref | 1 | value |  |  |  | fluid reference viscosity used in the equation of state. |
| wc_filerecord | 1 | record | out:? |  |  | name of the binary output file to write water content information. |
| wkt | 1 | value |  |  |  | is the coordinate reference system (CRS) well-known text (WKT) string. |
| xt3d | 1 | keyword |  |  |  | keyword that activates the XT3D formulation between the cells connected with this GWF-GWF Exchange. |
| xt3doptions | 1 | record |  | ixt3d(set_in=ar) ixt3drhs(set_in=ar) | 1/1 | none |
| zdisplacement_filerecord | 1 | record | out:? | zdispfn(set_in=ar) | 1/1 | name of the binary output file to write z-displacement information. |
| zero_order_decay_solid | 1 | keyword |  | ord0_decay_solid(set_in=ar) | 1/1 | is a text keyword to indicate that zero-order decay will occur in the solid phase. |
| zero_order_decay_water | 1 | keyword |  | ord0_decay_water(set_in=ar) | 1/1 | is a text keyword to indicate that zero-order decay will occur in the aqueous phase. |
