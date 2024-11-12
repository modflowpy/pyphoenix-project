# # Transient input variables

# MODFLOW stress period data is stored by FloPy as a dictionary of numpy
# recarrays, where each dictionary key is a zero-based stress period and each
# dictionary value is a recarray containing the stress period data for that
# stress period.  FloPy keeps this stress period data in a `MFTransientList`
# object and this data type is referred to as a transient list.
#
# FloPy accepts stress period data as a dictionary of numpy recarrays, but also
# supports replacing the recarrays with lists of tuples discussed above.
# Stress period data spanning multiple stress periods must be specified as a
# dictionary of lists where the dictionary key is the stress period expressed
# as a zero-based integer.
#
# The example below creates `stress_period_data` for the wel package with the
# first stress period containing a single well and the second stress period
# empty.  When empty stress period data is entered FloPy writes an empty
# stress period block to the package file.

from tempfile import TemporaryDirectory

import flopy
import numpy as np

# set up where simulation workspace will be stored
temp_dir = TemporaryDirectory()
workspace = temp_dir.name
name = "tutorial06_mf6_data"

# create the Flopy simulation and tdis objects
sim = flopy.mf6.MFSimulation(
    sim_name=name, exe_name="mf6", version="mf6", sim_ws=workspace
)
tdis = flopy.mf6.modflow.mftdis.ModflowTdis(
    sim,
    pname="tdis",
    time_units="DAYS",
    nper=2,
    perioddata=[(1.0, 1, 1.0), (1.0, 1, 1.0)],
)
# create the Flopy groundwater flow (gwf) model object
model_nam_file = f"{name}.nam"
gwf = flopy.mf6.ModflowGwf(sim, modelname=name, model_nam_file=model_nam_file)
# create the flopy iterative model solver (ims) package object
ims = flopy.mf6.modflow.mfims.ModflowIms(sim, pname="ims", complexity="SIMPLE")
# create the discretization package
bot = np.linspace(-50.0 / 3.0, -3.0, 3)
delrow = delcol = 4.0
dis = flopy.mf6.modflow.mfgwfdis.ModflowGwfdis(
    gwf,
    pname="dis",
    nogrb=True,
    nlay=3,
    nrow=10,
    ncol=10,
    delr=delrow,
    delc=delcol,
    top=0.0,
    botm=bot,
)

# First we create wel package with stress_period_data dictionary
# keys as zero-based integers so key "0" is stress period 1

stress_period_data = {
    0: [((2, 3, 1), -25.0)],  # stress period 1 well data
    1: [],
}  # stress period 2 well data is empty

# Then, using the dictionary created above, we build the wel package.

wel = flopy.mf6.ModflowGwfwel(
    gwf,
    print_input=True,
    print_flows=True,
    stress_period_data=stress_period_data,
    save_flows=False,
    pname="WEL-1",
)

# TODO typed API demo
