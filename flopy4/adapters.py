import os

from flopy.discretization.grid import Grid
from flopy.discretization.structuredgrid import StructuredGrid
from flopy.discretization.unstructuredgrid import UnstructuredGrid
from flopy.discretization.vertexgrid import VertexGrid


class StructuredGridWrapper(StructuredGrid):
    """
    Wrapper for StructuredGrid to add ia and ja properties.
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

        idomain = grb_obj.idomain
        xorigin = grb_obj.xorigin
        yorigin = grb_obj.yorigin
        angrot = grb_obj.angrot

        nlay, nrow, ncol = (grb_obj.nlay, grb_obj.nrow, grb_obj.ncol)
        delr, delc = grb_obj.delr, grb_obj.delc
        top, botm = grb_obj.top, grb_obj.bot
        top.shape = (nrow, ncol)
        botm.shape = (nlay, nrow, ncol)
        return cls(
            delc,
            delr,
            top,
            botm,
            idomain=idomain,
            xoff=xorigin,
            yoff=yorigin,
            angrot=angrot,
            ia=grb_obj.ia,
            ja=grb_obj.ja,
        )


def get_kij(nn: int, nlay: int, nrow: int, ncol: int) -> tuple[int, int, int]:
    nodes = nlay * nrow * ncol
    if nn < 0 or nn >= nodes:
        raise ValueError(f"Node number {nn} is out of bounds (1 to {nodes})")
    k = (nn - 1) / (ncol * nrow) + 1
    ij = nn - (k - 1) * ncol * nrow
    i = (ij - 1) / ncol + 1
    j = ij - (i - 1) * ncol
    return int(k), int(i), int(j)


def get_jk(nn: int, ncpl: int) -> tuple[int, int]:
    if nn < 0 or nn >= ncpl:
        raise ValueError(f"Node number {nn} is out of bounds (1 to {ncpl})")
    k = (nn - 1) / ncpl + 1
    j = nn - (k - 1) * ncpl
    return int(j), int(k)


def get_cellid(nn: int, grid: Grid) -> tuple[int, ...]:
    match grid:
        case StructuredGrid():
            return get_kij(nn, *grid.shape)
        case VertexGrid():
            return get_jk(nn, grid.ncpl)
        case UnstructuredGrid():
            return (nn,)
        case _:
            raise TypeError(f"Unsupported grid type: {type(grid)}")


def get_nn(cellid, **kwargs):
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
