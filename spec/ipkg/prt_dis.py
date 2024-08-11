# generated file
import numpy as np

from flopy4.array import MFArray
from flopy4.block import MFBlock
from flopy4.package import MFPackage
from flopy4.scalar import MFDouble, MFFilename, MFInteger, MFKeyword, MFString
from flopy4.compound import MFRecord

class PrtDis(MFPackage):
    length_units = MFString(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "model length units",
        description = "is the length units used for this model.  Values can be ``FEET'', ``METERS'', or ``CENTIMETERS''.  If not specified, the default is ``UNKNOWN''.",
    )
    nogrb = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "do not write binary grid file",
        description = "keyword to deactivate writing of the binary grid file.",
    )
    xorigin = MFDouble(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "x-position of the model grid origin",
        description = "x-position of the lower-left corner of the model grid.  A default value of zero is assigned if not specified.  The value for XORIGIN does not affect the model simulation, but it is written to the binary grid file so that postprocessors can locate the grid in space.",
    )
    yorigin = MFDouble(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "y-position of the model grid origin",
        description = "y-position of the lower-left corner of the model grid.  If not specified, then a default value equal to zero is used.  The value for YORIGIN does not affect the model simulation, but it is written to the binary grid file so that postprocessors can locate the grid in space.",
    )
    angrot = MFDouble(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "rotation angle",
        description = "counter-clockwise rotation angle (in degrees) of the lower-left corner of the model grid.  If not specified, then a default value of 0.0 is assigned.  The value for ANGROT does not affect the model simulation, but it is written to the binary grid file so that postprocessors can locate the grid in space.",
    )
    export_array_ascii = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "export array variables to layered ascii files.",
        description = "keyword that specifies input griddata arrays should be written to layered ascii output files.",
    )
    export_array_netcdf = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "export array variables to netcdf output files.",
        description = "keyword that specifies input griddata arrays should be written to the model output netcdf file.",
    )
    ncf_filerecord = MFRecord(
        params = {
            "ncf6": MFKeyword(),
            "filein": MFKeyword(),
            "ncf6_filename": MFString(),
        },
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "",
        description = "",
    )
    ncf6 = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "ncf keyword",
        description = "keyword to specify that record corresponds to a netcdf configuration (NCF) file.",
    )
    filein = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "file keyword",
        description = "keyword to specify that an input filename is expected next.",
    )
    ncf6_filename = MFString(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "file name of NCF information",
        description = "defines a netcdf configuration (NCF) input file.",
    )
    nlay = MFInteger(
        block = "dimensions",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "number of layers",
        description = "is the number of layers in the model grid.",
    )
    nrow = MFInteger(
        block = "dimensions",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "number of rows",
        description = "is the number of rows in the model grid.",
    )
    ncol = MFInteger(
        block = "dimensions",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "number of columns",
        description = "is the number of columns in the model grid.",
    )
    delr = MFArray(
        block = "griddata",
        shape = "(ncol)",
        reader = "readarray",
        optional = False,
        longname = "spacing along a row",
        description = "is the column spacing in the row direction.",
    )
    delc = MFArray(
        block = "griddata",
        shape = "(nrow)",
        reader = "readarray",
        optional = False,
        longname = "spacing along a column",
        description = "is the row spacing in the column direction.",
    )
    top = MFArray(
        block = "griddata",
        shape = "(ncol, nrow)",
        reader = "readarray",
        optional = False,
        longname = "cell top elevation",
        description = "is the top elevation for each cell in the top model layer.",
    )
    botm = MFArray(
        block = "griddata",
        shape = "(ncol, nrow, nlay)",
        reader = "readarray",
        optional = False,
        longname = "cell bottom elevation",
        description = "is the bottom elevation for each cell.",
    )
    idomain = MFArray(
        block = "griddata",
        shape = "(ncol, nrow, nlay)",
        reader = "readarray",
        optional = True,
        longname = "idomain existence array",
        description = "is an optional array that characterizes the existence status of a cell.  If the IDOMAIN array is not specified, then all model cells exist within the solution.  If the IDOMAIN value for a cell is 0, the cell does not exist in the simulation.  Input and output values will be read and written for the cell, but internal to the program, the cell is excluded from the solution.  If the IDOMAIN value for a cell is 1, the cell exists in the simulation.  If the IDOMAIN value for a cell is -1, the cell does not exist in the simulation.  Furthermore, the first existing cell above will be connected to the first existing cell below.  This type of cell is referred to as a ``vertical pass through'' cell.",
    )