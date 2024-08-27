# generated file
from flopy4.array import MFArray
from flopy4.compound import MFRecord, MFList
from flopy4.package import MFPackage
from flopy4.scalar import MFDouble, MFFilename, MFInteger, MFKeyword, MFString


class SimNam(MFPackage):
    multipkg = False
    stress = False
    advanced = False

    # TODO this is hand edited to avoid python continue namespace collision
    todo_continue = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""continue if not converged""",
        description =
"""keyword flag to indicate that the simulation should continue even if
one or more solutions do not converge.""",
    )

    nocheck = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""turn off checking""",
        description =
"""keyword flag to indicate that the model input check routines should
not be called prior to each time step. Checks are performed by
default.""",
    )

    memory_print_option = MFString(
        type = "string",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""memory print option""",
        description =
"""is a flag that controls printing of detailed memory manager usage to
the end of the simulation list file.  NONE means do not print detailed
information. SUMMARY means print only the total memory for each
simulation component. ALL means print information for each variable
stored in the memory manager. NONE is default if MEMORY_PRINT_OPTION
is not specified.""",
    )

    maxerrors = MFInteger(
        type = "integer",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""maximum number of errors""",
        description =
"""maximum number of errors that will be stored and printed.""",
    )

    print_input = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""print input to listing file""",
        description =
"""keyword to activate printing of simulation input summaries to the
simulation list file (mfsim.lst). With this keyword, input summaries
will be written for those packages that support newer input data model
routines.  Not all packages are supported yet by the newer input data
model routines.""",
    )

    hpc_filerecord = MFRecord(
        type = "record",
        params = {
            "hpc6": MFKeyword(),
            "filein": MFKeyword(),
            "hpc6_filename": MFString(),
        },
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""""",
        description =
"""hpc record""",
    )

    hpc6 = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""head keyword""",
        description =
"""keyword to specify that record corresponds to a hpc file.""",
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

    hpc6_filename = MFString(
        type = "string",
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""file name of time series information""",
        description =
"""name of input file to define HPC file settings for the HPC package.
See the ``HPC File'' section for instructions for preparing HPC input
files.""",
    )

    tdis6 = MFString(
        type = "string",
        block = "timing",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""name of tdis input file""",
        description =
"""is the name of the Temporal Discretization (TDIS) Input File.""",
    )

    mtype = MFString(
        type = "string",
        block = "models",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""model type""",
        description =
"""is the type of model to add to simulation.""",
    )

    mfname = MFString(
        type = "string",
        block = "models",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""file name for model name file""",
        description =
"""is the file name of the model name file.""",
    )

    mname = MFString(
        type = "string",
        block = "models",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""name of model""",
        description =
"""is the user-assigned name of the model.  The model name cannot exceed
16 characters and must not have blanks within the name.  The model
name is case insensitive; any lowercase letters are converted and
stored as upper case letters.""",
    )

    models = MFList(
        type = "recarray",
        params = {
            "mtype": mtype,
            "mfname": mfname,
            "mname": mname,
        },
        block = "models",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""list of models""",
        description =
"""is the list of model types, model name files, and model names.""",
    )

    exgtype = MFString(
        type = "string",
        block = "exchanges",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""exchange type""",
        description =
"""is the exchange type.""",
    )

    exgfile = MFString(
        type = "string",
        block = "exchanges",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""input file for exchange""",
        description =
"""is the input file for the exchange.""",
    )

    exgmnamea = MFString(
        type = "string",
        block = "exchanges",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""name of model A""",
        description =
"""is the name of the first model that is part of this exchange.""",
    )

    exgmnameb = MFString(
        type = "string",
        block = "exchanges",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""name of model B""",
        description =
"""is the name of the second model that is part of this exchange.""",
    )

    exchanges = MFList(
        type = "recarray",
        params = {
            "exgtype": exgtype,
            "exgfile": exgfile,
            "exgmnamea": exgmnamea,
            "exgmnameb": exgmnameb,
        },
        block = "exchanges",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""list of exchanges""",
        description =
"""is the list of exchange types, exchange files, and model names.""",
    )

    mxiter = MFInteger(
        type = "integer",
        block = "solutiongroup",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""maximum solution group iterations""",
        description =
"""is the maximum number of outer iterations for this solution group.
The default value is 1.  If there is only one solution in the solution
group, then MXITER must be 1.""",
    )

    slntype = MFString(
        type = "string",
        block = "solutiongroup",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""type of solution""",
        description =
"""is the type of solution.  The Integrated Model Solution (IMS6) and
Explicit Model Solution (EMS6) are the only supported options in this
version.""",
    )

    slnfname = MFString(
        type = "string",
        block = "solutiongroup",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""file name for solution input""",
        description =
"""name of file containing solution input.""",
    )

    slnmnames = MFString(
        type = "string",
        block = "solutiongroup",
        shape = "(:)",
        reader = "urword",
        optional = False,
        longname =
"""array of model names in this solution""",
        description =
"""is the array of model names to add to this solution.  The number of
model names is determined by the number of model names the user
provides on this line.""",
    )

    solutiongroup = MFList(
        type = "recarray",
        params = {
            "slntype": slntype,
            "slnfname": slnfname,
            "slnmnames": slnmnames,
        },
        block = "solutiongroup",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""solution type and models in the solution""",
        description =
"""is the list of solution types and models in the solution.""",
    )
