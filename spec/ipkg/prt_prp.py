import numpy as np

from flopy4.array import MFArray
from flopy4.block import MFBlock
from flopy4.package import MFPackage
from flopy4.scalar import MFDouble, MFFilename, MFInteger, MFKeyword, MFString
from flopy4.compound import MFRecord

# generated file
class PrtPrp(MFPackage):
    boundnames = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "",
        description = "keyword to indicate that boundary names may be provided with the list of particle release points.",
    )
    print_input = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "print input to listing file",
        description = "REPLACE print_input {'{#1}': 'all model stress package'}",
    )
    dev_exit_solve_method = MFInteger(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "exit solve method",
        description = "the method for iterative solution of particle exit location and time in the generalized Pollock's method.  0 default, 1 Brent, 2 Chandrupatla.  The default is Brent's method.",
    )
    exit_solve_tolerance = MFDouble(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "exit solve tolerance",
        description = "the convergence tolerance for iterative solution of particle exit location and time in the generalized Pollock's method.  A value of 0.00001 works well for many problems, but the value that strikes the best balance between accuracy and runtime is problem-dependent.",
    )
    local_z = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "whether to use local z coordinates",
        description = "indicates that ``zrpt'' defines the local z coordinate of the release point within the cell, with value of 0 at the bottom and 1 at the top of the cell.  If the cell is partially saturated at release time, the top of the cell is considered to be the water table elevation (the head in the cell) rather than the top defined by the user.",
    )
    extend_tracking = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "whether to extend tracking beyond the end of the simulation",
        description = "indicates that particles should be tracked beyond the end of the simulation's final time step (using that time step's flows) until particles terminate or reach a specified stop time.  By default, particles are terminated at the end of the simulation's final time step.",
    )
    track_filerecord = MFRecord(
        params = {
            "track": MFKeyword(),
            "fileout": MFKeyword(),
            "trackfile": MFString(),
        },
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "",
        description = "",
    )
    track = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "track keyword",
        description = "keyword to specify that record corresponds to a binary track output file.  Each PRP Package may have a distinct binary track output file.",
    )
    fileout = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "file keyword",
        description = "keyword to specify that an output filename is expected next.",
    )
    trackfile = MFString(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "file keyword",
        description = "name of the binary output file to write tracking information.",
    )
    trackcsv_filerecord = MFRecord(
        params = {
            "trackcsv": MFKeyword(),
            "fileout": MFKeyword(),
            "trackcsvfile": MFString(),
        },
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "",
        description = "",
    )
    trackcsv = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "track keyword",
        description = "keyword to specify that record corresponds to a CSV track output file.  Each PRP Package may have a distinct CSV track output file.",
    )
    trackcsvfile = MFString(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "file keyword",
        description = "name of the comma-separated value (CSV) file to write tracking information.",
    )
    stoptime = MFDouble(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "stop time",
        description = "real value defining the maximum simulation time to which particles in the package can be tracked.  Particles that have not terminated earlier due to another termination condition will terminate when simulation time STOPTIME is reached.  If the last stress period in the simulation consists of more than one time step, particles will not be tracked past the ending time of the last stress period, regardless of STOPTIME.  If the last stress period in the simulation consists of a single time step, it is assumed to be a steady-state stress period, and its ending time will not limit the simulation time to which particles can be tracked.  If STOPTIME and STOPTRAVELTIME are both provided, particles will be stopped if either is reached.",
    )
    stoptraveltime = MFDouble(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "stop travel time",
        description = "real value defining the maximum travel time over which particles in the model can be tracked.  Particles that have not terminated earlier due to another termination condition will terminate when their travel time reaches STOPTRAVELTIME.  If the last stress period in the simulation consists of more than one time step, particles will not be tracked past the ending time of the last stress period, regardless of STOPTRAVELTIME.  If the last stress period in the simulation consists of a single time step, it is assumed to be a steady-state stress period, and its ending time will not limit the travel time over which particles can be tracked.  If STOPTIME and STOPTRAVELTIME are both provided, particles will be stopped if either is reached.",
    )
    stop_at_weak_sink = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "stop at weak sink",
        description = "is a text keyword to indicate that a particle is to terminate when it enters a cell that is a weak sink.  By default, particles are allowed to pass though cells that are weak sinks.",
    )
    istopzone = MFInteger(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "stop zone number",
        description = "integer value defining the stop zone number.  If cells have been assigned IZONE values in the GRIDDATA block, a particle terminates if it enters a cell whose IZONE value matches ISTOPZONE.  An ISTOPZONE value of zero indicates that there is no stop zone.  The default value is zero.",
    )
    drape = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "drape",
        description = "is a text keyword to indicate that if a particle's release point is in a cell that happens to be inactive at release time, the particle is to be moved to the topmost active cell below it, if any. By default, a particle is not released into the simulation if its release point's cell is inactive at release time.",
    )
    release_timesrecord = MFRecord(
        params = {
            "release_times": MFKeyword(),
            "times": MFArray(shape="(unknown)"),
        },
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "",
        description = "",
    )
    release_times = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "",
        description = "keyword indicating release times will follow",
    )
    times = MFArray(
        block = "options",
        shape = "(unknown)",
        reader = "urword",
        optional = False,
        longname = "release times",
        description = "times to release, relative to the beginning of the simulation.  RELEASE_TIMES and RELEASE_TIMESFILE are mutually exclusive.",
    )
    release_timesfilerecord = MFRecord(
        params = {
            "release_timesfile": MFKeyword(),
            "timesfile": MFString(),
        },
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "",
        description = "",
    )
    release_timesfile = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "",
        description = "keyword indicating release times file name will follow",
    )
    timesfile = MFString(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "file keyword",
        description = "name of the release times file.  RELEASE_TIMES and RELEASE_TIMESFILE are mutually exclusive.",
    )
    dev_forceternary = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "force ternary tracking method",
        description = "force use of the ternary tracking method regardless of cell type in DISV grids.",
    )
    nreleasepts = MFInteger(
        block = "dimensions",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "number of particle release points",
        description = "is the number of particle release points.",
    )
    irptno = MFInteger(
        block = "packagedata",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "PRP id number for release point",
        description = "integer value that defines the PRP release point number associated with the specified PACKAGEDATA data on the line. IRPTNO must be greater than zero and less than or equal to NRELEASEPTS.  The program will terminate with an error if information for a PRP release point number is specified more than once.",
    )
    cellid = MFArray(
        block = "packagedata",
        shape = "(ncelldim)",
        reader = "urword",
        optional = False,
        longname = "cell identifier",
        description = "REPLACE cellid {}",
    )
    xrpt = MFDouble(
        block = "packagedata",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "x coordinate of release point",
        description = "real value that defines the x coordinate of the release point in model coordinates.  The (x, y, z) location specified for the release point must lie within the cell that is identified by the specified cellid.",
    )
    yrpt = MFDouble(
        block = "packagedata",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "y coordinate of release point",
        description = "real value that defines the y coordinate of the release point in model coordinates.  The (x, y, z) location specified for the release point must lie within the cell that is identified by the specified cellid.",
    )
    zrpt = MFDouble(
        block = "packagedata",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "z coordinate of release point",
        description = "real value that defines the z coordinate of the release point in model coordinates or, if the LOCAL_Z option is active, in local cell coordinates.  The (x, y, z) location specified for the release point must lie within the cell that is identified by the specified cellid.",
    )
    boundname = MFString(
        block = "packagedata",
        shape = "",
        reader = "urword",
        optional = True,
        longname = "release point name",
        description = "name of the particle release point. BOUNDNAME is an ASCII character variable that can contain as many as 40 characters. If BOUNDNAME contains spaces in it, then the entire name must be enclosed within single quotes.",
    )
    all = MFKeyword(
        block = "period",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "",
        description = "keyword to indicate release of particles at the start of all time steps in the period.",
    )
    first = MFKeyword(
        block = "period",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "",
        description = "keyword to indicate release of particles at the start of the first time step in the period. This keyword may be used in conjunction with other keywords to release particles at the start of multiple time steps.",
    )
    frequency = MFInteger(
        block = "period",
        shape = "",
        reader = "urword",
        optional = False,
        longname = "",
        description = "release particles at the specified time step frequency. This keyword may be used in conjunction with other keywords to release particles at the start of multiple time steps.",
    )
    steps = MFArray(
        block = "period",
        shape = "(<nstp)",
        reader = "urword",
        optional = False,
        longname = "",
        description = "release particles at the start of each step specified in STEPS. This keyword may be used in conjunction with other keywords to release particles at the start of multiple time steps.",
    )
    fraction = MFArray(
        block = "period",
        shape = "(<nstp)",
        reader = "urword",
        optional = True,
        longname = "",
        description = "release particles after the specified fraction of the time step has elapsed. If FRACTION is not set, particles are released at the start of the specified time step(s). FRACTION must be a single value when used with ALL, FIRST, or FREQUENCY. When used with STEPS, FRACTION may be a single value or an array of the same length as STEPS. If a single FRACTION value is provided with STEPS, the fraction applies to all steps.",
    )