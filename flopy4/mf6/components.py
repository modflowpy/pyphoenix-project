from abc import ABC
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional
from attr import Factory, define, field
from xarray import DataTree

import numpy as np
from numpy.typing import NDArray

from flopy4.component import component, setattr, resolve_array, init_tree
from flopy4.utils import to_path


class Package(ABC):
    data: DataTree = None


class Model(ABC):
    data: DataTree = None


class Sim(ABC):
    data: DataTree = None


# @component could in theory wrap the @define decorator
@component
@define(init=False, slots=False, on_setattr=setattr)
class Dis(Package):
    length_units: str = field(
        # store block as metadata then dynamically
        # discover and expose blocks as properties.
        default=None,
        metadata={"block": "options"},
        # OR, blocks could be attrs classes too...
        # that will be necessary if variable names
        # at the top level are not unique, but they
        # currently are (if we like that constraint
        # we should document it and enforce it when
        # DFNs are loaded?)
    )
    nogrb: bool = field(default=False, metadata={"block": "options"})
    xorigin: float = field(default=None, metadata={"block": "options"})
    yorigin: float = field(default=None, metadata={"block": "options"})
    angrot: float = field(default=None, metadata={"block": "options"})
    export_array_netcdf: bool = field(
        default=False, metadata={"block": "options"}
    )
    nlay: int = field(default=1, metadata={"block": "dimensions"})
    ncol: int = field(default=2, metadata={"block": "dimensions"})
    nrow: int = field(default=2, metadata={"block": "dimensions"})
    delr: NDArray[np.floating] = field(
        # we use a converter both to resolve an array shape
        # and check it, handling both conversion/validation
        converter=resolve_array,
        default=1.0,
        metadata={"block": "griddata", "shape": "(ncol,)"},
    )
    delc: NDArray[np.floating] = field(
        converter=resolve_array,
        default=1.0,
        metadata={"block": "griddata", "shape": "(nrow,)"},
    )
    top: NDArray[np.floating] = field(
        converter=resolve_array,
        default=1.0,
        metadata={"block": "griddata", "shape": "(ncol, nrow)"},
    )
    botm: NDArray[np.floating] = field(
        converter=resolve_array,
        default=0.0,
        metadata={"block": "griddata", "shape": "(ncol, nrow, nlay)"},
    )
    idomain: Optional[NDArray[np.integer]] = field(
        converter=resolve_array,
        default=1,
        metadata={"block": "griddata", "shape": "(ncol, nrow, nlay)"},
    )
    nodes: Optional[int] = field(default=None)

    def __init__(
        self=None,
        model=None,
        length_units=None,
        nogrb=False,
        xorigin=None,
        yorigin=None,
        angrot=None,
        export_array_netcdf=False,
        nlay=1,
        ncol=2,
        nrow=2,
        delr=1.0,
        delc=1.0,
        top=1.0,
        botm=0.0,
        idomain=1,
    ):
        init_tree(
            self,
            parent=model,
            length_units=length_units,
            nogrb=nogrb,
            xorigin=xorigin,
            yorigin=yorigin,
            angrot=angrot,
            export_array_netcdf=export_array_netcdf,
            nlay=nlay,
            ncol=ncol,
            nrow=nrow,
            nodes=ncol * nrow * nlay,
            delr=delr,
            delc=delc,
            top=top,
            botm=botm,
            idomain=idomain,
        )


@component
@define(init=False, slots=False, on_setattr=setattr)
class Ic(Package):
    strt: NDArray[np.floating] = field(
        converter=resolve_array,
        default=1.0,
        metadata={"block": "packagedata", "shape": "(nodes)"},
    )
    export_array_ascii: bool = field(
        default=False, metadata={"block": "options"}
    )
    export_array_netcdf: bool = field(
        default=False,
        metadata={"block": "options"},
    )

    def __init__(
        self,
        model=None,
        strt=1.0,
        export_array_ascii=False,
        export_array_netcdf=False,
    ):
        init_tree(
            self,
            parent=model,
            strt=strt,
            export_array_ascii=export_array_ascii,
            export_array_netcdf=export_array_netcdf,
        )


@component
@define(init=False, slots=False, on_setattr=setattr)
class Oc(Package):
    @define(slots=False)
    class Format:
        columns: int = field(default=10)
        width: int = field(default=11)
        digits: int = field(default=4)
        format: Literal["exponential", "fixed", "general", "scientific"] = (
            field(default="general")
        )

    @define(slots=False)
    class Steps:
        first: Optional[Literal["first"]] = field(default="first")
        last: Optional[Literal["last"]] = field(default=None)
        all: Optional[Literal["all"]] = field(default=None)
        frequency: Optional[int] = field(default=None)
        steps: Optional[list[int]] = field(default=None)

    budget_file: Optional[Path] = field(
        converter=to_path,
        default=None,
        metadata={"block": "options"},
    )
    budget_csv_file: Optional[Path] = field(
        converter=to_path,
        default=None,
        metadata={"block": "options"},
    )
    head_file: Optional[Path] = field(
        converter=to_path,
        default=None,
        metadata={"block": "options"},
    )
    printhead: Optional[Format] = field(
        default=None, init=False, metadata={"block": "options"}
    )
    perioddata: list[Steps] = field(
        default=Factory(list),
        metadata={"block": "perioddata", "shape": "(nper,)"},
    )

    def __init__(
        self,
        model=None,
        budget_file=None,
        budget_csv_file=None,
        head_file=None,
        printhead=None,
        perioddata=None,
    ):
        init_tree(
            self,
            parent=model,
            budget_file=budget_file,
            budget_csv_file=budget_csv_file,
            head_file=head_file,
            printhead=printhead,
            perioddata=perioddata,
        )


@component
@define(init=False, slots=False, on_setattr=setattr)
class Npf(Package):
    # no options, just arrays for now
    icelltype: NDArray[np.integer] = field(
        converter=resolve_array,
        default=0,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )
    k: NDArray[np.floating] = field(
        converter=resolve_array,
        default=1.0,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )
    k22: Optional[NDArray[np.floating]] = field(
        converter=resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )
    k33: Optional[NDArray[np.floating]] = field(
        converter=resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )
    angle1: Optional[NDArray[np.floating]] = field(
        converter=resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )
    angle2: Optional[NDArray[np.floating]] = field(
        converter=resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )
    angle3: Optional[NDArray[np.floating]] = field(
        converter=resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )
    wetdry: Optional[NDArray[np.floating]] = field(
        converter=resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )

    def __init__(
        self,
        model=None,
        icelltype=0,
        k=1.0,
        k22=None,
        k33=None,
        angle1=None,
        angle2=None,
        angle3=None,
        wetdry=None,
    ):
        init_tree(
            self,
            parent=model,
            icelltype=icelltype,
            k=k,
            k22=k22,
            k33=k33,
            angle1=angle1,
            angle2=angle2,
            angle3=angle3,
            wetdry=wetdry,
        )


@component
@define(init=False, slots=False)
class Gwf(Model):
    def __init__(
        self,
        sim=None,
    ):
        init_tree(self, parent=sim)


@component
@define(init=False, slots=False, on_setattr=setattr)
class Tdis(Package):
    @define(slots=False)
    class PeriodData:
        perlen: float = field(default=1.0)
        nstp: int = field(default=1)
        tsmult: float = field(default=1.0)

    nper: int = field(default=1, metadata={"block": "dimensions"})
    perioddata: list[PeriodData] = field(
        default=Factory(list),
        metadata={"block": "perioddata", "shape": "(nper)"},
    )
    time_units: Optional[str] = field(
        default=None, metadata={"block": "options"}
    )
    start_date_time: Optional[datetime] = field(
        default=None, metadata={"block": "options"}
    )

    def __init__(
        self,
        sim=None,
        nper=1,
        perioddata=None,
        time_units=None,
        start_date_time=None,
    ):
        init_tree(
            self,
            parent=sim,
            nper=nper,
            perioddata=perioddata,
            time_units=time_units,
            start_date_time=start_date_time,
        )


@component
@define(slots=False)
class Simulation(Sim):
    def __init__(self):
        init_tree(self)
