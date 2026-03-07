import os
from typing import Any

import numpy as np
import scipy.sparse
import xugrid as xu
from flopy.discretization.structuredgrid import StructuredGrid

__all__ = [
    "StructuredGridWrapper",
    "read_binary_grid_file",
    "get_nn",
]


class StructuredGridWrapper(StructuredGrid):
    """
    Wrapper for StructuredGrid to add ia and ja properties.

    ``ia`` and ``ja`` follow the same 0-based CSR convention returned by
    :class:`flopy.mf6.utils.binarygrid_util.MfGrdFile` (which converts the
    Fortran 1-based arrays to 0-based on read).  All DISV connectivity arrays
    in this module use the same 0-based convention.

    TODO: add this to flopy3 and this can be removed.
    """

    def __init__(
        self,
        delc=None,
        delr=None,
        top=None,
        botm=None,
        idomain=None,
        lenuni=None,
        crs=None,
        prjfile=None,
        xoff=0.0,
        yoff=0.0,
        angrot=0.0,
        nlay=None,
        nrow=None,
        ncol=None,
        laycbd=None,
        ia=None,
        ja=None,
        **kwargs,
    ):
        super().__init__(
            delc=delc,
            delr=delr,
            top=top,
            botm=botm,
            idomain=idomain,
            lenuni=lenuni,
            crs=crs,
            prjfile=prjfile,
            xoff=xoff,
            yoff=yoff,
            angrot=angrot,
            nlay=nlay,
            nrow=nrow,
            ncol=ncol,
            laycbd=laycbd,
            **kwargs,
        )

        self._ia = ia
        self._ja = ja

    @property
    def ja(self):
        return self._ja

    @property
    def ia(self):
        return self._ia

    @classmethod
    def _from_grb(cls, grb_obj):
        """
        Construct from an already-opened :class:`~flopy.mf6.utils.binarygrid_util.MfGrdFile`.

        Parameters
        ----------
        grb_obj : MfGrdFile
            An already-opened binary grid file object for a DIS grid.

        Returns
        -------
        StructuredGridWrapper
        """
        crs = grb_obj._datadict["CRS"] if grb_obj._version == "2" else None
        nlay, nrow, ncol = (grb_obj.nlay, grb_obj.nrow, grb_obj.ncol)
        delr, delc = grb_obj.delr, grb_obj.delc
        top, botm = grb_obj.top, grb_obj.bot
        top.shape = (nrow, ncol)
        botm.shape = (nlay, nrow, ncol)
        # ia and ja are already 0-based (MfGrdFile subtracts 1 from the
        # Fortran 1-based arrays stored in the binary file).
        return cls(
            delc,
            delr,
            top,
            botm,
            idomain=grb_obj.idomain,
            crs=crs,
            xoff=grb_obj.xorigin,
            yoff=grb_obj.yorigin,
            angrot=grb_obj.angrot,
            ia=grb_obj.ia,
            ja=grb_obj.ja,
        )

    @classmethod
    def from_binary_grid_file(cls, file_path, verbose=False):
        """
        Instantiate a StructuredGrid model grid from a MODFLOW 6 binary
        grid (*.grb) file.

        Parameters
        ----------
        file_path : str
            file path for the MODFLOW 6 binary grid file
        verbose : bool
            Write information to standard output.  Default is False.

        Returns
        -------
        return : StructuredGrid

        """
        from flopy.mf6.utils.binarygrid_util import MfGrdFile

        grb_obj = MfGrdFile(file_path, verbose=verbose)
        if grb_obj.grid_type != "DIS":
            raise ValueError(
                f"Binary grid file ({os.path.basename(file_path)}) is not a structured (DIS) grid."
            )
        return cls._from_grb(grb_obj)


def _ugrid_iavert_javert(iavert: np.ndarray, javert: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert MODFLOW 6 iavert/javert (0-based) to UGRID conventions.
    Removes the closing vertex from each cell's vertex list.

    Parameters
    ----------
    iavert : 0-based indptr array (from MfGrdFile), shape (ncpl+1,)
    javert : 0-based vertex indices (from MfGrdFile), shape (njavert,)

    Returns
    -------
    ia : 0-based indptr for UGRID (no closing vertex)
    ja : 0-based vertex indices for UGRID
    """
    # Each cell's vertex list has one extra closing vertex (first == last).
    # Remove it for UGRID conventions.
    n = np.diff(iavert) - 1  # number of unique vertices per cell
    ia = np.concatenate(([0], np.cumsum(n)))
    keep = np.ones_like(javert, dtype=bool)
    # The closing vertex of each cell is at position iavert[i+1] - 1
    closing_indices = iavert[1:] - 1
    keep[closing_indices] = False
    return ia, javert[keep]


def read_binary_grid_file(file_path: str | os.PathLike, verbose: bool = False) -> dict[str, Any]:
    """
    Read a MODFLOW 6 binary grid (GRB) file and return grid info.

    Parameters
    ----------
    file_path : str or Path
        Path to the MODFLOW 6 binary grid file.
    verbose : bool, optional
        Print info to stdout. Default False.

    Returns
    -------
    dict
        Grid info dictionary.
    """
    from flopy.mf6.utils.binarygrid_util import MfGrdFile

    grb = MfGrdFile(file_path, verbose=verbose)

    if grb.grid_type == "DIS":
        # Use the already-opened grb object — avoids reading the file twice.
        grid = StructuredGridWrapper._from_grb(grb)
        return {"grid_type": "DIS", "grid": grid}

    elif grb.grid_type == "DISV":
        return _read_disv_grb(grb)

    else:
        raise ValueError(
            f"Unsupported grid type '{grb.grid_type}' in {os.path.basename(str(file_path))}. "
            "Only DIS and DISV are supported."
        )


def _read_disv_grb(grb) -> dict[str, Any]:
    nlay = grb.nlay
    ncpl = grb.ncpl
    ncells = nlay * ncpl
    # ia and ja are already 0-based (MfGrdFile subtracts 1 from the Fortran
    # 1-based arrays on read).  All connectivity helpers in cbc_reader expect
    # 0-based CSR arrays.
    ia = grb.ia
    ja = grb.ja

    # Get vertex data (0-based from MfGrdFile)
    iavert_0 = grb.iavert
    javert_0 = grb.javert

    # Convert iavert/javert to UGRID conventions (remove closing vertex)
    ugrid_ia, ugrid_ja = _ugrid_iavert_javert(iavert_0, javert_0)

    # Build Ugrid2d from vertex info
    verts = grb.verts
    xorigin = grb.xorigin
    yorigin = grb.yorigin
    node_x = verts[:, 0] + xorigin
    node_y = verts[:, 1] + yorigin

    n_nodes = len(verts)
    ncpl_faces = len(ugrid_ia) - 1
    face_nodes = scipy.sparse.csr_matrix(
        (np.ones(len(ugrid_ja), dtype=np.intp), ugrid_ja, ugrid_ia),
        shape=(ncpl_faces, n_nodes),
    )
    grid = xu.Ugrid2d(node_x, node_y, -1, face_nodes)
    facedim = grid.face_dimension

    idomain = grb.idomain.reshape((nlay, ncpl))

    coords = {"layer": np.arange(1, nlay + 1)}
    crs = grb._datadict["CRS"] if grb._version == "2" else None

    return {
        "grid_type": "DISV",
        "grid": grid,
        "nlayer": nlay,
        "ncells_per_layer": ncpl,
        "ncells": ncells,
        "nja": grb._datadict.get("NJA", ia[-1] - 1),
        "ia": ia,
        "ja": ja,
        "idomain": idomain,
        "coords": coords,
        "face_dimension": facedim,
        "crs": crs,
    }


def get_nn(cellid, **kwargs) -> int:
    """
    Convert a cell ID tuple to a flat node number (0-based).

    Parameters
    ----------
    cellid : tuple
        - 1-element: (node,) — unstructured or DISV node number
        - 2-element: (layer, cell) — DISV (k, j)
        - 3-element: (layer, row, col) — DIS (k, i, j)
    **kwargs
        Dimension sizes: ``ncpl`` for DISV, ``nrow``/``ncol`` for DIS.

    Returns
    -------
    int
        0-based flat node index.
    """
    ndim = len(cellid)
    match ndim:
        case 1:
            return cellid[0]
        case 2:
            k, j = cellid
            return k * kwargs["ncpl"] + j
        case 3:
            k, i, j = cellid
            return k * kwargs["nrow"] * kwargs["ncol"] + i * kwargs["ncol"] + j
        case _:
            raise ValueError(f"Invalid cellid: {cellid}")
