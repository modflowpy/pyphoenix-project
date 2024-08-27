# generated file
from flopy4.array import MFArray
from flopy4.compound import MFRecord, MFList
from flopy4.package import MFPackage
from flopy4.scalar import MFDouble, MFFilename, MFInteger, MFKeyword, MFString


class ExgGwfgwf(MFPackage):
    multipkg = False
    stress = False
    advanced = False

    auxiliary = MFString(
        type = "string",
        block = "options",
        shape = "(naux)",
        reader = "urword",
        optional = True,
        longname =
"""keyword to specify aux variables""",
        description =
"""an array of auxiliary variable names.  There is no limit on the number
of auxiliary variables that can be provided. Most auxiliary variables
will not be used by the GWF-GWF Exchange, but they will be available
for use by other parts of the program.  If an auxiliary variable with
the name ``ANGLDEGX'' is found, then this information will be used as
the angle (provided in degrees) between the connection face normal and
the x axis, where a value of zero indicates that a normal vector
points directly along the positive x axis.  The connection face normal
is a normal vector on the cell face shared between the cell in model 1
and the cell in model 2 pointing away from the model 1 cell.
Additional information on ``ANGLDEGX'' and when it is required is
provided in the description of the DISU Package.  If an auxiliary
variable with the name ``CDIST'' is found, then this information will
be used in the calculation of specific discharge within model cells
connected by the exchange.  For a horizontal connection, CDIST should
be specified as the horizontal distance between the cell centers, and
should not include the vertical component.  For vertical connections,
CDIST should be specified as the difference in elevation between the
two cell centers.  Both ANGLDEGX and CDIST are required if specific
discharge is calculated for either of the groundwater models.""",
    )

    boundnames = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""""",
        description =
"""REPLACE boundnames {'{#1}': 'GWF Exchange'}""",
    )

    print_input = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""keyword to print input to list file""",
        description =
"""keyword to indicate that the list of exchange entries will be echoed
to the listing file immediately after it is read.""",
    )

    print_flows = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""keyword to print gwfgwf flows to list file""",
        description =
"""keyword to indicate that the list of exchange flow rates will be
printed to the listing file for every stress period in which ``SAVE
BUDGET'' is specified in Output Control.""",
    )

    save_flows = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""keyword to save GWFGWF flows""",
        description =
"""keyword to indicate that cell-by-cell flow terms will be written to
the budget file for each model provided that the Output Control for
the models are set up with the ``BUDGET SAVE FILE'' option.""",
    )

    cell_averaging = MFString(
        type = "string",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""conductance weighting option""",
        description =
"""is a keyword and text keyword to indicate the method that will be used
for calculating the conductance for horizontal cell connections.  The
text value for CELL_AVERAGING can be ``HARMONIC'', ``LOGARITHMIC'', or
``AMT-LMK'', which means ``arithmetic-mean thickness and logarithmic-
mean hydraulic conductivity''. If the user does not specify a value
for CELL_AVERAGING, then the harmonic-mean method will be used.""",
    )

    cvoptions = MFRecord(
        type = "record",
        params = {
            "variablecv": MFKeyword(),
            "dewatered": MFKeyword(),
        },
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""vertical conductance options""",
        description =
"""none""",
    )

    variablecv = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""keyword to activate VARIABLECV option""",
        description =
"""keyword to indicate that the vertical conductance will be calculated
using the saturated thickness and properties of the overlying cell and
the thickness and properties of the underlying cell.  If the DEWATERED
keyword is also specified, then the vertical conductance is calculated
using only the saturated thickness and properties of the overlying
cell if the head in the underlying cell is below its top.  If these
keywords are not specified, then the default condition is to calculate
the vertical conductance at the start of the simulation using the
initial head and the cell properties.  The vertical conductance
remains constant for the entire simulation.""",
    )

    dewatered = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""keyword to activate DEWATERED option""",
        description =
"""If the DEWATERED keyword is specified, then the vertical conductance
is calculated using only the saturated thickness and properties of the
overlying cell if the head in the underlying cell is below its top.""",
    )

    newton = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""keyword to activate Newton-Raphson""",
        description =
"""keyword that activates the Newton-Raphson formulation for groundwater
flow between connected, convertible groundwater cells. Cells will not
dry when this option is used.""",
    )

    xt3d = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""keyword to activate XT3D""",
        description =
"""keyword that activates the XT3D formulation between the cells
connected with this GWF-GWF Exchange.""",
    )

    gnc_filerecord = MFRecord(
        type = "record",
        params = {
            "gnc6": MFKeyword(),
            "filein": MFKeyword(),
            "gnc6_filename": MFString(),
        },
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""""",
        description =
"""""",
    )

    filein = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""file keyword""",
        description =
"""keyword to specify that an input filename is expected next.""",
    )

    gnc6 = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""gnc6 keyword""",
        description =
"""keyword to specify that record corresponds to a ghost-node correction
file.""",
    )

    gnc6_filename = MFString(
        type = "string",
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""gnc6 input filename""",
        description =
"""is the file name for ghost node correction input file.  Information
for the ghost nodes are provided in the file provided with these
keywords.  The format for specifying the ghost nodes is the same as
described for the GNC Package of the GWF Model.  This includes
specifying OPTIONS, DIMENSIONS, and GNCDATA blocks.  The order of the
ghost nodes must follow the same order as the order of the cells in
the EXCHANGEDATA block.  For the GNCDATA, noden and all of the nodej
values are assumed to be located in model 1, and nodem is assumed to
be in model 2.""",
    )

    mvr_filerecord = MFRecord(
        type = "record",
        params = {
            "mvr6": MFKeyword(),
            "filein": MFKeyword(),
            "mvr6_filename": MFString(),
        },
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""""",
        description =
"""""",
    )

    mvr6 = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""obs keyword""",
        description =
"""keyword to specify that record corresponds to a mover file.""",
    )

    mvr6_filename = MFString(
        type = "string",
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""mvr6 input filename""",
        description =
"""is the file name of the water mover input file to apply to this
exchange.  Information for the water mover are provided in the file
provided with these keywords.  The format for specifying the water
mover information is the same as described for the Water Mover (MVR)
Package of the GWF Model, with two exceptions.  First, in the PACKAGES
block, the model name must be included as a separate string before
each package.  Second, the appropriate model name must be included
before package name 1 and package name 2 in the BEGIN PERIOD block.
This allows providers and receivers to be located in both models
listed as part of this exchange.""",
    )

    obs_filerecord = MFRecord(
        type = "record",
        params = {
            "obs6": MFKeyword(),
            "filein": MFKeyword(),
            "obs6_filename": MFString(),
        },
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""""",
        description =
"""""",
    )

    obs6 = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""obs keyword""",
        description =
"""keyword to specify that record corresponds to an observations file.""",
    )

    obs6_filename = MFString(
        type = "string",
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""obs6 input filename""",
        description =
"""is the file name of the observations input file for this exchange. See
the ``Observation utility'' section for instructions for preparing
observation input files. Table ref{table:gwf-obstypetable} lists
observation type(s) supported by the GWF-GWF package.""",
    )

    dev_interfacemodel_on = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""activate interface model on exchange""",
        description =
"""activates the interface model mechanism for calculating the
coefficients at (and possibly near) the exchange. This keyword should
only be used for development purposes.""",
    )

    nexg = MFInteger(
        type = "integer",
        block = "dimensions",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""number of exchanges""",
        description =
"""keyword and integer value specifying the number of GWF-GWF exchanges.""",
    )

    cellidm1 = MFInteger(
        type = "integer",
        block = "exchangedata",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""cellid of first cell""",
        description =
"""is the cellid of the cell in model 1 as specified in the simulation
name file. For a structured grid that uses the DIS input file,
CELLIDM1 is the layer, row, and column numbers of the cell.   For a
grid that uses the DISV input file, CELLIDM1 is the layer number and
CELL2D number for the two cells.  If the model uses the unstructured
discretization (DISU) input file, then CELLIDM1 is the node number for
the cell.""",
    )

    cellidm2 = MFInteger(
        type = "integer",
        block = "exchangedata",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""cellid of second cell""",
        description =
"""is the cellid of the cell in model 2 as specified in the simulation
name file. For a structured grid that uses the DIS input file,
CELLIDM2 is the layer, row, and column numbers of the cell.   For a
grid that uses the DISV input file, CELLIDM2 is the layer number and
CELL2D number for the two cells.  If the model uses the unstructured
discretization (DISU) input file, then CELLIDM2 is the node number for
the cell.""",
    )

    ihc = MFInteger(
        type = "integer",
        block = "exchangedata",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""integer flag for connection type""",
        description =
"""is an integer flag indicating the direction between node n and all of
its m connections. If IHC = 0 then the connection is vertical.  If IHC
= 1 then the connection is horizontal. If IHC = 2 then the connection
is horizontal for a vertically staggered grid.""",
    )

    cl1 = MFDouble(
        type = "double",
        block = "exchangedata",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""connection distance""",
        description =
"""is the distance between the center of cell 1 and the its shared face
with cell 2.""",
    )

    cl2 = MFDouble(
        type = "double",
        block = "exchangedata",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""connection distance""",
        description =
"""is the distance between the center of cell 2 and the its shared face
with cell 1.""",
    )

    hwva = MFDouble(
        type = "double",
        block = "exchangedata",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""horizontal cell width or area for vertical flow""",
        description =
"""is the horizontal width of the flow connection between cell 1 and cell
2 if IHC $>$ 0, or it is the area perpendicular to flow of the
vertical connection between cell 1 and cell 2 if IHC = 0.""",
    )

    aux = MFArray(
        type = "array",
        block = "exchangedata",
        shape = "(naux)",
        reader = "urword",
        optional = True,
        longname =
"""auxiliary variables""",
        description =
"""represents the values of the auxiliary variables for each GWFGWF
Exchange. The values of auxiliary variables must be present for each
exchange. The values must be specified in the order of the auxiliary
variables specified in the OPTIONS block.""",
    )

    boundname = MFString(
        type = "string",
        block = "exchangedata",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""exchange boundname""",
        description =
"""REPLACE boundname {'{#1}': 'GWF Exchange'}""",
    )

    exchangedata = MFList(
        type = "recarray",
        params = {
            "cellidm1": cellidm1,
            "cellidm2": cellidm2,
            "ihc": ihc,
            "cl1": cl1,
            "cl2": cl2,
            "hwva": hwva,
            "aux": aux,
            "boundname": boundname,
        },
        block = "exchangedata",
        shape = "(nexg)",
        reader = "urword",
        optional = False,
        longname =
"""exchange data""",
        description =
"""""",
    )