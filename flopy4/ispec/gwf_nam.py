# generated file
from flopy4.array import MFArray
from flopy4.compound import MFRecord, MFList
from flopy4.package import MFPackage
from flopy4.scalar import MFDouble, MFFilename, MFInteger, MFKeyword, MFString


class GwfNam(MFPackage):
    multipkg = False
    stress = False
    advanced = False

    list = MFString(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""name of listing file""",
        description =
"""is name of the listing file to create for this GWF model.  If not
specified, then the name of the list file will be the basename of the
GWF model name file and the '.lst' extension.  For example, if the GWF
name file is called ``my.model.nam'' then the list file will be called
``my.model.lst''.""",
    )

    print_input = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""print input to listing file""",
        description =
"""REPLACE print_input {'{#1}': 'all model stress package'}""",
    )

    print_flows = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""print calculated flows to listing file""",
        description =
"""REPLACE print_flows {'{#1}': 'all model package'}""",
    )

    save_flows = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""save flows for all packages to budget file""",
        description =
"""REPLACE save_flows {'{#1}': 'all model package'}""",
    )

    newtonoptions = MFRecord(
        params = {
            "newton": MFKeyword(),
            "under_relaxation": MFKeyword(),
        },
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""newton keyword and options""",
        description =
"""none""",
    )

    newton = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""keyword to activate Newton-Raphson formulation""",
        description =
"""keyword that activates the Newton-Raphson formulation for groundwater
flow between connected, convertible groundwater cells and stress
packages that support calculation of Newton-Raphson terms for
groundwater exchanges. Cells will not dry when this option is used. By
default, the Newton-Raphson formulation is not applied.""",
    )

    under_relaxation = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""keyword to activate Newton-Raphson UNDER_RELAXATION option""",
        description =
"""keyword that indicates whether the groundwater head in a cell will be
under-relaxed when water levels fall below the bottom of the model
below any given cell. By default, Newton-Raphson UNDER_RELAXATION is
not applied.""",
    )

    export_netcdf = MFString(
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""export model output netcdf file.""",
        description =
"""keyword that specifies timeseries data for the dependent variable
should be written to a model output netcdf file.  No value or
``UGRID'' (ugrid based export) values are supported.""",
    )

    nc_filerecord = MFRecord(
        params = {
            "netcdf": MFKeyword(),
            "filein": MFKeyword(),
            "netcdf_filename": MFString(),
        },
        block = "options",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""""",
        description =
"""netcdf config filerecord""",
    )

    netcdf = MFKeyword(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""netcdf keyword""",
        description =
"""keyword to specify that record corresponds to a netcdf input file.""",
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

    netcdf_filename = MFString(
        block = "options",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""netcdf input filename""",
        description =
"""defines a netcdf input file.""",
    )

    ftype = MFString(
        block = "packages",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""package type""",
        description =
"""is the file type, which must be one of the following character values
shown in table~ref{table:ftype-gwf}. Ftype may be entered in any
combination of uppercase and lowercase.""",
    )

    fname = MFString(
        block = "packages",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""file name""",
        description =
"""is the name of the file containing the package input.  The path to the
file should be included if the file is not located in the folder where
the program was run.""",
    )

    pname = MFString(
        block = "packages",
        shape = "",
        reader = "urword",
        optional = True,
        longname =
"""user name for package""",
        description =
"""is the user-defined name for the package. PNAME is restricted to 16
characters.  No spaces are allowed in PNAME.  PNAME character values
are read and stored by the program for stress packages only.  These
names may be useful for labeling purposes when multiple stress
packages of the same type are located within a single GWF Model.  If
PNAME is specified for a stress package, then PNAME will be used in
the flow budget table in the listing file; it will also be used for
the text entry in the cell-by-cell budget file.  PNAME is case
insensitive and is stored in all upper case letters.""",
    )

    packages = MFList(
        params = {
            "ftype": ftype,
            "fname": fname,
            "pname": pname,
        },
        block = "packages",
        shape = "",
        reader = "urword",
        optional = False,
        longname =
"""package list""",
        description =
"""""",
    )