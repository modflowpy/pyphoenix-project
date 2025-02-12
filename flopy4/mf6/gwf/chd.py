from pathlib import Path
from typing import Optional

from attr import define, field

from flopy4 import component, setattribute
from flopy4.mf6 import Package


@component(align="nper")
@define(slots=False, on_setattr=setattribute)
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
        default=None,
        metadata={"block": "period", "dims": ("nper")},
        # converter=lambda d: structure_spd(d),
    )

    # def structure_spd(d) -> Optional[list[list[StressPeriodData]]]:
    #     if d is None:
    #         return None
    #     if instance(d, dict):
    #         pass
    #     if isinstance(d, list):

    #         def _structure_period(l):
    #             return [structure_attrs_fromtuple(t) for t in l]

    #         a = np.array(d)
    #         match a.ndim:
    #             case 1:
    #                 period = _structure_period(a)
    #             case 2:
    #                 pass
    #             case _:
    #                 raise ValueError(
    #                     "CHD stress period data must be 1D or 2D"
    #                 )
