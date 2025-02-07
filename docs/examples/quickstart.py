import flopy4
ws = './mymodel'
name = 'mymodel'
sim = flopy4.mf6.MFSimulation(sim_name=name, sim_ws=ws, exe_name='mf6')
tdis = flopy4.mf6.ModflowTdis(sim)
ims = flopy4.mf6.ModflowIms(sim)
gwf = flopy4.mf6.ModflowGwf(sim, modelname=name, save_flows=True)
dis = flopy4.mf6.ModflowGwfdis(gwf, nrow=10, ncol=10)
ic = flopy4.mf6.ModflowGwfic(gwf)
npf = flopy4.mf6.ModflowGwfnpf(gwf, save_specific_discharge=True)
chd = flopy4.mf6.ModflowGwfchd(gwf) # self.stress_period_data = sparse.DOK((ncol, nrow, nlay))
chd.stress_period_data[0,0,0] = 1.
chd.stress_period_data[0,9,9] = 0.

# chd = flopy4.mf6.ModflowGwfchd(gwf, stress_period_data=sparse.COO([[0,0], [0,9], [0,9]], [1., 0.]))
# chd = flopy4.mf6.ModflowGwfchd(gwf, stress_period_data=[Chd.PeriodData((0, 0, 0), 1.),
#                                                        Chd.PeriodData[(0, 9, 9), 0.]])
budget_file = name + '.bud'
head_file = name + '.hds'
oc = flopy4.mf6.ModflowGwfoc(gwf,
                            budget_filerecord=budget_file,
                            head_filerecord=head_file,
                            save={tis.get_period("10-20-2020"): {"head": "ALL", "budget": "ALL"}}
                            print={"budget": np.ones()}
                            # save_head="ALL",
                            # save_budget=np.ones(nstp),
                            # print_head="",
                            # print_budget="",
oc.saverecord["HEAD"]="ALL"
oc.saverecord["BUDGET"]=np.ones((nstp))

# Normally you would write and run the simulation
# sim.write_simulation()
# sim.run_simulation()


head = gwf.output.head().get_data()
bud = gwf.output.budget()

spdis = bud.get_data(text='DATA-SPDIS')[0]
qx, qy, qz = flopy.utils.postprocessing.get_specific_discharge(spdis, gwf)
pmv = flopy.plot.PlotMapView(gwf)
pmv.plot_array(head)
pmv.plot_grid(colors='white')
pmv.contour_array(head, levels=[.2, .4, .6, .8], linewidths=3.)
pmv.plot_vector(qx, qy, normalize=True, color="white")




# from demo:

# # Create a simulation.
# 
# sim = Simulation()
# tdis = Tdis(sim=sim, nper=1, perioddata=[Tdis.PeriodData()])
# gwf = Gwf(sim=sim)
# dis = Dis(model=gwf)
# ic = Ic(model=gwf, strt=1.0)
# oc = Oc(model=gwf, perioddata=[Oc.Steps()])
# npf = Npf(model=gwf, icelltype=0, k=1.0)
# 
# # View the data tree.
# sim.data