# # Record and union variables
#
# This example demonstrates how to work with record and union input
# variables.
#
# A record variable is a product type. Record fields can be scalars,
# other record variables, or unions of such.
#
# A union (keystring) variable is a sum type.
#
# MODFLOW 6 represents records as (possibly variadic) tuples. FloPy
# supports both a low-level tuple interface for records, conforming
# to MODFLOW 6, and a high-level, strongly-typed record interface.

# package import
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

# ## Adding MODFLOW Package Data, Connection Data, and Option Lists
#
# MODFLOW Package data, connection data, and option lists are stored by FloPy
# as numpy recarrays.  FloPy does accept numpy recarrays as input, but does
# has other supported formats discussed below.
#
# MODFLOW option lists that only contain a single row or data can be either
# specified by:
#
# 1. Specifying a string containing the entire line as it would be displayed
#    in the package file (`rewet_record="REWET WETFCT 1.0 IWETIT 1 IHDWET 0"`)
# 2. Specifying the data in a tuple within a list
#    (`rewet_record=[("WETFCT", 1.0, "IWETIT", 1, "IHDWET", 0)]`)
#
# In the example below the npf package is created setting the `rewet_record`
# option to a string of text as would be typed into the package file.

npf = flopy.mf6.modflow.mfgwfnpf.ModflowGwfnpf(
    gwf,
    rewet_record="REWET WETFCT 1.0 IWETIT 1 IHDWET 0",
    pname="npf",
    icelltype=1,
    k=1.0,
    save_flows=True,
    xt3doptions="xt3d rhs",
)

# `rewet_record` is then set using the npf package's `rewet_record` property.
# This time 'rewet_record' is defined using a tuple within a list.

npf.rewet_record = [("WETFCT", 1.1, "IWETIT", 0, "IHDWET", 1)]

# TODO: typed API demo
