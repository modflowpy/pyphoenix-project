# generated file
from flopy4.array import MFArray
from flopy4.compound import MFRecord, MFList
from flopy4.package import MFPackage
from flopy4.scalar import MFDouble, MFFilename, MFInteger, MFKeyword, MFString


class SimTdis(MFPackage):
    multipkg = False
    stress = False
    advanced = False

    time_units = MFString(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""time unit""",
        description =
"""is the time units of the simulation.  This is a text string that is
used as a label within model output files.  Values for time_units may
be ``unknown'',  ``seconds'', ``minutes'', ``hours'', ``days'', or
``years''.  The default time unit is ``unknown''.""",
    )

    start_date_time = MFString(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""starting date and time""",
        description =
"""is the starting date and time of the simulation.  This is a text
string that is used as a label within the simulation list file.  The
value has no effect on the simulation.  The recommended format for the
starting date and time is described at https://www.w3.org/TR/NOTE-
datetime.""",
    )

    ats_filerecord = MFRecord(
        params = {
            "ats6": MFKeyword(),
            "filein": MFKeyword(),
            "ats6_filename": MFString(),
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

    ats6 = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""ats keyword""",
        description =
"""keyword to specify that record corresponds to an adaptive time step
(ATS) input file.  The behavior of ATS and a description of the input
file is provided separately.""",
    )

    filein = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""file keyword""",
        description =
"""keyword to specify that an input filename is expected next.""",
    )

    ats6_filename = MFString(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""file name of adaptive time series information""",
        description =
"""defines an adaptive time step (ATS) input file defining ATS controls.
Records in the ATS file can be used to override the time step behavior
for selected stress periods.""",
    )

    nper = MFInteger(
        block = "dimensions",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""number of stress periods""",
        description =
"""is the number of stress periods for the simulation.""",
    )

    perlen = MFDouble(
        block = "perioddata",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""length of stress period""",
        description =
"""is the length of a stress period.""",
    )

    nstp = MFInteger(
        block = "perioddata",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""number of time steps""",
        description =
"""is the number of time steps in a stress period.""",
    )

    tsmult = MFDouble(
        block = "perioddata",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""number of time steps""",
        description =
"""is the multiplier for the length of successive time steps. The length
of a time step is calculated by multiplying the length of the previous
time step by TSMULT. The length of the first time step, $Delta t_1$,
is related to PERLEN, NSTP, and TSMULT by the relation $Delta t_1=
perlen frac{tsmult - 1}{tsmult^{nstp}-1}$.""",
    )

    perioddata = MFList(
        params = {
            "perlen": perlen,
            "nstp": nstp,
            "tsmult": tsmult,
        },
        block = "perioddata",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""stress period time information""",
        description =
"""""",
    )