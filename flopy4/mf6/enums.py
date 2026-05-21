from enum import Enum


class NetCDFFormat(str, Enum):
    """NetCDF output format type.

    LAYERED_MESH  — UGRID 2-D layered mesh topology (``mesh="layered"``
                    attribute in the output file; corresponds to the MODFLOW 6
                    ``NETCDF_MESH2D`` input keyword).
    STRUCTURED    — CF-convention structured grid; no mesh topology in the
                    output file.

    A future ``UNSTRUCTURED_MESH`` value will represent the UGRID fully-3D
    unstructured (non-layered) mesh topology once that spec is finalised and
    MODFLOW 6 support is added.
    """

    LAYERED_MESH = "layered"
    STRUCTURED = "structured"
