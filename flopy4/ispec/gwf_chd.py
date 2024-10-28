# generated file
from flopy4.array import MFArray
from flopy4.compound import MFRecord, MFList
from flopy4.package import MFPackage
from flopy4.scalar import MFDouble, MFFilename, MFInteger, MFKeyword, MFString


class GwfChd(MFPackage):
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
"""REPLACE auxnames {'{#1}': 'Groundwater Flow'}""",
    )

    auxmultname = MFString(
        type = "string",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""name of auxiliary variable for multiplier""",
        description =
"""REPLACE auxmultname {'{#1}': 'CHD head value'}""",
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
"""REPLACE boundnames {'{#1}': 'constant-head'}""",
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
"""REPLACE print_input {'{#1}': 'constant-head'}""",
    )

    print_flows = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""print CHD flows to listing file""",
        description =
"""REPLACE print_flows {'{#1}': 'constant-head'}""",
    )

    save_flows = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""save CHD flows to budget file""",
        description =
"""REPLACE save_flows {'{#1}': 'constant-head'}""",
    )

    ts_filerecord = MFRecord(
        type = "record",
        params = {
            "ts6": MFKeyword(),
            "filein": MFKeyword(),
            "ts6_filename": MFString(),
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

    ts6 = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""head keyword""",
        description =
"""keyword to specify that record corresponds to a time-series file.""",
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

    ts6_filename = MFString(
        type = "string",
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""file name of time series information""",
        description =
"""REPLACE timeseriesfile {}""",
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
"""REPLACE obs6_filename {'{#1}': 'constant-head'}""",
    )

    dev_no_newton = MFKeyword(
        type = "keyword",
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""turn off Newton for unconfined cells""",
        description =
"""turn off Newton for unconfined cells""",
    )

    maxbound = MFInteger(
        type = "integer",
        block = "dimensions",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""maximum number of constant heads""",
        description =
"""REPLACE maxbound {'{#1}': 'constant-head'}""",
    )

    cellid = MFArray(
        type = "integer",
        block = "period",
        shape = "(ncelldim)",
        reader = "urword",
        optional = False,
        longname =
"""cell identifier""",
        description =
"""REPLACE cellid {}""",
    )

    head = MFDouble(
        type = "double",
        block = "period",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""head value assigned to constant head""",
        description =
"""is the head at the boundary. If the Options block includes a
TIMESERIESFILE entry (see the ``Time-Variable Input'' section), values
can be obtained from a time series by entering the time-series name in
place of a numeric value.""",
    )

    aux = MFArray(
        type = "double",
        block = "period",
        shape = "(naux)",
        reader = "urword",
        optional = True,
        longname =
"""auxiliary variables""",
        description =
"""REPLACE aux {'{#1}': 'constant head'}""",
    )

    boundname = MFString(
        type = "string",
        block = "period",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""constant head boundary name""",
        description =
"""REPLACE boundname {'{#1}': 'constant head boundary'}""",
    )

    stress_period_data = MFList(
        type = "recarray",
        params = {
            "cellid": cellid,
            "head": head,
            "aux": aux,
            "boundname": boundname,
        },
        block = "period",
        shape = "(maxbound)",
        reader = "urword",
        optional = False,
        longname =
"""""",
        description =
"""""",
    )