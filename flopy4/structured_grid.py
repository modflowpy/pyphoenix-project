import os

from flopy.discretization import StructuredGrid


class StructuredGridWrapper(StructuredGrid):
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
                f"Binary grid file ({os.path.basename(file_path)}) "
                "is not a structured (DIS) grid."
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
