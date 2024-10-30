# generated file
from flopy4.array import MFArray
from flopy4.compound import MFRecord, MFList
from flopy4.package import MFPackage
from flopy4.scalar import MFDouble, MFFilename, MFInteger, MFKeyword, MFString


class GwtDisv(MFPackage):
    multipkg = False
    stress = False
    advanced = False

    length_units = MFString(
        type = "string",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""model length units""",
        description =
"""is the length units used for this model.  Values can be ``FEET'',
``METERS'', or ``CENTIMETERS''.  If not specified, the default is
``UNKNOWN''.""",
    )

    nogrb = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""do not write binary grid file""",
        description =
"""keyword to deactivate writing of the binary grid file.""",
    )

    xorigin = MFDouble(
        type = "double",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""x-position origin of the model grid coordinate system""",
        description =
"""x-position of the origin used for model grid vertices.  This value
should be provided in a real-world coordinate system.  A default value
of zero is assigned if not specified.  The value for XORIGIN does not
affect the model simulation, but it is written to the binary grid file
so that postprocessors can locate the grid in space.""",
    )

    yorigin = MFDouble(
        type = "double",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""y-position origin of the model grid coordinate system""",
        description =
"""y-position of the origin used for model grid vertices.  This value
should be provided in a real-world coordinate system.  If not
specified, then a default value equal to zero is used.  The value for
YORIGIN does not affect the model simulation, but it is written to the
binary grid file so that postprocessors can locate the grid in space.""",
    )

    angrot = MFDouble(
        type = "double",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""rotation angle""",
        description =
"""counter-clockwise rotation angle (in degrees) of the model grid
coordinate system relative to a real-world coordinate system.  If not
specified, then a default value of 0.0 is assigned.  The value for
ANGROT does not affect the model simulation, but it is written to the
binary grid file so that postprocessors can locate the grid in space.""",
    )

    export_array_ascii = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""export array variables to layered ascii files.""",
        description =
"""keyword that specifies input griddata arrays should be written to
layered ascii output files.""",
    )

    export_array_netcdf = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""export array variables to netcdf output files.""",
        description =
"""keyword that specifies input griddata arrays should be written to the
model output netcdf file.""",
    )

    ncf_filerecord = MFRecord(
        type = "record",
        params = {
            "ncf6": MFKeyword(),
            "filein": MFKeyword(),
            "ncf6_filename": MFString(),
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

    ncf6 = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""ncf keyword""",
        description =
"""keyword to specify that record corresponds to a netcdf configuration
(NCF) file.""",
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

    ncf6_filename = MFString(
        type = "string",
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""file name of NCF information""",
        description =
"""defines a netcdf configuration (NCF) input file.""",
    )

    nlay = MFInteger(
        type = "integer",
        block = "dimensions",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""number of layers""",
        description =
"""is the number of layers in the model grid.""",
    )

    ncpl = MFInteger(
        type = "integer",
        block = "dimensions",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""number of cells per layer""",
        description =
"""is the number of cells per layer.  This is a constant value for the
grid and it applies to all layers.""",
    )

    nvert = MFInteger(
        type = "integer",
        block = "dimensions",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""number of columns""",
        description =
"""is the total number of (x, y) vertex pairs used to characterize the
horizontal configuration of the model grid.""",
    )

    top = MFArray(
        type = "double",
        block = "griddata",
        shape = "(ncpl)",
        reader = "readarray",
        optional = False,
        longname =
"""model top elevation""",
        description =
"""is the top elevation for each cell in the top model layer.""",
    )

    botm = MFArray(
        type = "double",
        block = "griddata",
        shape = "(ncpl, nlay)",
        reader = "readarray",
        optional = False,
        longname =
"""model bottom elevation""",
        description =
"""is the bottom elevation for each cell.""",
    )

    idomain = MFArray(
        type = "integer",
        block = "griddata",
        shape = "(ncpl, nlay)",
        reader = "readarray",
        optional = True,
        longname =
"""idomain existence array""",
        description =
"""is an optional array that characterizes the existence status of a
cell.  If the IDOMAIN array is not specified, then all model cells
exist within the solution.  If the IDOMAIN value for a cell is 0, the
cell does not exist in the simulation.  Input and output values will
be read and written for the cell, but internal to the program, the
cell is excluded from the solution.  If the IDOMAIN value for a cell
is 1, the cell exists in the simulation.  If the IDOMAIN value for a
cell is -1, the cell does not exist in the simulation.  Furthermore,
the first existing cell above will be connected to the first existing
cell below.  This type of cell is referred to as a ``vertical pass
through'' cell.""",
    )

    iv = MFInteger(
        type = "integer",
        block = "vertices",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""vertex number""",
        description =
"""is the vertex number.  Records in the VERTICES block must be listed in
consecutive order from 1 to NVERT.""",
    )

    xv = MFDouble(
        type = "double",
        block = "vertices",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""x-coordinate for vertex""",
        description =
"""is the x-coordinate for the vertex.""",
    )

    yv = MFDouble(
        type = "double",
        block = "vertices",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""y-coordinate for vertex""",
        description =
"""is the y-coordinate for the vertex.""",
    )

    vertices = MFList(
        type = "recarray",
        params = {
            "iv": iv,
            "xv": xv,
            "yv": yv,
        },
        block = "vertices",
        shape = "(nvert)",
        reader = "urword",
        optional = False,
        longname =
"""vertices data""",
        description =
"""""",
    )

    icell2d = MFInteger(
        type = "integer",
        block = "cell2d",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""cell2d number""",
        description =
"""is the CELL2D number.  Records in the CELL2D block must be listed in
consecutive order from the first to the last.""",
    )

    xc = MFDouble(
        type = "double",
        block = "cell2d",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""x-coordinate for cell center""",
        description =
"""is the x-coordinate for the cell center.""",
    )

    yc = MFDouble(
        type = "double",
        block = "cell2d",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""y-coordinate for cell center""",
        description =
"""is the y-coordinate for the cell center.""",
    )

    ncvert = MFInteger(
        type = "integer",
        block = "cell2d",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""number of cell vertices""",
        description =
"""is the number of vertices required to define the cell.  There may be a
different number of vertices for each cell.""",
    )

    icvert = MFArray(
        type = "integer",
        block = "cell2d",
        shape = "(ncvert)",
        reader = "urword",
        optional = False,
        longname =
"""array of vertex numbers""",
        description =
"""is an array of integer values containing vertex numbers (in the
VERTICES block) used to define the cell.  Vertices must be listed in
clockwise order.  Cells that are connected must share vertices.""",
    )

    cell2d = MFList(
        type = "recarray",
        params = {
            "icell2d": icell2d,
            "xc": xc,
            "yc": yc,
            "ncvert": ncvert,
            "icvert": icvert,
        },
        block = "cell2d",
        shape = "(ncpl)",
        reader = "urword",
        optional = False,
        longname =
"""cell2d data""",
        description =
"""""",
    )