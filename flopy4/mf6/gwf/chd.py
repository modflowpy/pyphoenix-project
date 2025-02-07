from pathlib import Path
from typing import Optional

from attr import define, field

from flopy4 import component, init_tree, setattribute
from flopy4.mf6 import Package


@component
@define(init=False, slots=False, on_setattr=setattribute)
class Chd(Package):
    multi = True

    @define(slots=False)
    class StressPeriodData:
        cellid: tuple[int, ...] = field()
        head: float = field()
        aux: Optional[float] = field(default=None)
        boundname: Optional[str] = field(default=None)

    auxiliary: Optional[list[str]] = field(
        default=None, metadata={"block": "options"}
    )
    auxmultname: Optional[str] = field(
        default=None, metadata={"block": "options"}
    )
    boundnames: bool = field(default=False, metadata={"block": "options"})
    print_input: bool = field(default=False, metadata={"block": "options"})
    print_flows: bool = field(default=False, metadata={"block": "options"})
    save_flows: bool = field(default=False, metadata={"block": "options"})
    ts_filerecord: Optional[Path] = field(
        default=None, metadata={"block": "options"}
    )
    obs_filerecord: Optional[Path] = field(
        default=None, metadata={"block": "options"}
    )
    dev_no_newton: bool = field(default=False, metadata={"block": "options"})
    maxbound: Optional[int] = field(
        default=None, metadata={"block": "dimensions"}
    )
    stress_period_data: Optional[list[list[StressPeriodData]]] = field(
        default=None, metadata={"block": "period"}
    )

    def __init__(
        self,
        model=None,
        name=None,
        path=None,
        auxiliary=None,
        auxmultname=None,
        boundnames=None,
        print_input=False,
        print_flows=False,
        save_flows=False,
        ts_filerecord=None,
        obs_filerecord=None,
        dev_no_newton=None,
        maxbound=None,
        stress_period_data=None,
    ):
        super().__init__(name, path)
        init_tree(
            self,
            parent=model,
            auxiliary=auxiliary,
            auxmultname=auxmultname,
            boundnames=boundnames,
            print_input=print_input,
            print_flows=print_flows,
            save_flows=save_flows,
            ts_filerecord=ts_filerecord,
            obs_filerecord=obs_filerecord,
            dev_no_newton=dev_no_newton,
            maxbound=maxbound,
            stress_period_data=stress_period_data,
        )
