# generated file
from flopy4.array import MFArray
from flopy4.compound import MFRecord, MFList
from flopy4.package import MFPackage
from flopy4.scalar import MFDouble, MFFilename, MFInteger, MFKeyword, MFString


class GwfDisu(MFPackage):
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

    vertical_offset_tolerance = MFDouble(
        type = "double",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""vertical length dimension for top and bottom checking""",
        description =
"""checks are performed to ensure that the top of a cell is not higher
than the bottom of an overlying cell.  This option can be used to
specify the tolerance that is used for checking.  If top of a cell is
above the bottom of an overlying cell by a value less than this
tolerance, then the program will not terminate with an error.  The
default value is zero.  This option should generally not be used.""",
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

    nodes = MFInteger(
        type = "integer",
        block = "dimensions",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""number of layers""",
        description =
"""is the number of cells in the model grid.""",
    )

    nja = MFInteger(
        type = "integer",
        block = "dimensions",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""number of columns""",
        description =
"""is the sum of the number of connections and NODES.  When calculating
the total number of connections, the connection between cell n and
cell m is considered to be different from the connection between cell
m and cell n.  Thus, NJA is equal to the total number of connections,
including n to m and m to n, and the total number of cells.""",
    )

    nvert = MFInteger(
        type = "integer",
        block = "dimensions",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""number of vertices""",
        description =
"""is the total number of (x, y) vertex pairs used to define the plan-
view shape of each cell in the model grid.  If NVERT is not specified
or is specified as zero, then the VERTICES and CELL2D blocks below are
not read.  NVERT and the accompanying VERTICES and CELL2D blocks
should be specified for most simulations.  If the XT3D or
SAVE_SPECIFIC_DISCHARGE options are specified in the NPF Package, then
this information is required.""",
    )

    top = MFArray(
        type = "double",
        block = "griddata",
        shape = "(nodes)",
        reader = "readarray",
        optional = False,
        longname =
"""cell top elevation""",
        description =
"""is the top elevation for each cell in the model grid.""",
    )

    bot = MFArray(
        type = "double",
        block = "griddata",
        shape = "(nodes)",
        reader = "readarray",
        optional = False,
        longname =
"""cell bottom elevation""",
        description =
"""is the bottom elevation for each cell.""",
    )

    area = MFArray(
        type = "double",
        block = "griddata",
        shape = "(nodes)",
        reader = "readarray",
        optional = False,
        longname =
"""cell surface area""",
        description =
"""is the cell surface area (in plan view).""",
    )

    idomain = MFArray(
        type = "integer",
        block = "griddata",
        shape = "(nodes)",
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
is 1 or greater, the cell exists in the simulation.  IDOMAIN values of
-1 cannot be specified for the DISU Package.""",
    )

    iac = MFArray(
        type = "integer",
        block = "connectiondata",
        shape = "(nodes)",
        reader = "readarray",
        optional = False,
        longname =
"""number of cell connections""",
        description =
"""is the number of connections (plus 1) for each cell.  The sum of all
the entries in IAC must be equal to NJA.""",
    )

    ja = MFArray(
        type = "integer",
        block = "connectiondata",
        shape = "(nja)",
        reader = "readarray",
        optional = False,
        longname =
"""grid connectivity""",
        description =
"""is a list of cell number (n) followed by its connecting cell numbers
(m) for each of the m cells connected to cell n. The number of values
to provide for cell n is IAC(n).  This list is sequentially provided
for the first to the last cell. The first value in the list must be
cell n itself, and the remaining cells must be listed in an increasing
order (sorted from lowest number to highest).  Note that the cell and
its connections are only supplied for the GWF cells and their
connections to the other GWF cells.  Also note that the JA list input
may be divided such that every node and its connectivity list can be
on a separate line for ease in readability of the file. To further
ease readability of the file, the node number of the cell whose
connectivity is subsequently listed, may be expressed as a negative
number, the sign of which is subsequently converted to positive by the
code.""",
    )

    ihc = MFArray(
        type = "integer",
        block = "connectiondata",
        shape = "(nja)",
        reader = "readarray",
        optional = False,
        longname =
"""connection type""",
        description =
"""is an index array indicating the direction between node n and all of
its m connections.  If IHC = 0 then cell n and cell m are connected in
the vertical direction.  Cell n overlies cell m if the cell number for
n is less than m; cell m overlies cell n if the cell number for m is
less than n.  If IHC = 1 then cell n and cell m are connected in the
horizontal direction.  If IHC = 2 then cell n and cell m are connected
in the horizontal direction, and the connection is vertically
staggered.  A vertically staggered connection is one in which a cell
is horizontally connected to more than one cell in a horizontal
connection.""",
    )

    cl12 = MFArray(
        type = "double",
        block = "connectiondata",
        shape = "(nja)",
        reader = "readarray",
        optional = False,
        longname =
"""connection lengths""",
        description =
"""is the array containing connection lengths between the center of cell
n and the shared face with each adjacent m cell.""",
    )

    hwva = MFArray(
        type = "double",
        block = "connectiondata",
        shape = "(nja)",
        reader = "readarray",
        optional = False,
        longname =
"""connection lengths""",
        description =
"""is a symmetric array of size NJA.  For horizontal connections, entries
in HWVA are the horizontal width perpendicular to flow.  For vertical
connections, entries in HWVA are the vertical area for flow.  Thus,
values in the HWVA array contain dimensions of both length and area.
Entries in the HWVA array have a one-to-one correspondence with the
connections specified in the JA array.  Likewise, there is a one-to-
one correspondence between entries in the HWVA array and entries in
the IHC array, which specifies the connection type (horizontal or
vertical).  Entries in the HWVA array must be symmetric; the program
will terminate with an error if the value for HWVA for an n to m
connection does not equal the value for HWVA for the corresponding n
to m connection.""",
    )

    angldegx = MFArray(
        type = "double",
        block = "connectiondata",
        shape = "(nja)",
        reader = "readarray",
        optional = True,
        longname =
"""angle of face normal to connection""",
        description =
"""is the angle (in degrees) between the horizontal x-axis and the
outward normal to the face between a cell and its connecting cells.
The angle varies between zero and 360.0 degrees, where zero degrees
points in the positive x-axis direction, and 90 degrees points in the
positive y-axis direction.  ANGLDEGX is only needed if horizontal
anisotropy is specified in the NPF Package, if the XT3D option is used
in the NPF Package, or if the SAVE_SPECIFIC_DISCHARGE option is
specified in the NPF Package.  ANGLDEGX does not need to be specified
if these conditions are not met.  ANGLDEGX is of size NJA; values
specified for vertical connections and for the diagonal position are
not used.  Note that ANGLDEGX is read in degrees, which is different
from MODFLOW-USG, which reads a similar variable (ANGLEX) in radians.""",
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
        optional = True,
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
"""is the cell2d number.  Records in the CELL2D block must be listed in
consecutive order from 1 to NODES.""",
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
clockwise order.""",
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
        shape = "(nodes)",
        reader = "urword",
        optional = True,
        longname =
"""cell2d data""",
        description =
"""""",
    )