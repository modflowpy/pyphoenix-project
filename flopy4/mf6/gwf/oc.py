from pathlib import Path
from typing import Literal, Optional

from attr import Factory, define, field

from flopy4 import component, init_tree, setattribute
from flopy4.mf6 import Package
from flopy4.utils import to_path

Steps = (
    Literal["all"] | Literal["first"] | Literal["last"] | tuple[str | int, ...]
)


@component
@define(init=False, slots=False, on_setattr=setattribute)
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
    class Period:
        rtype: str = field()
        steps: Steps = field()

    @define
    class Steps_:
        steps: Steps = field()

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
    format: Optional[Format] = field(
        default=None, init=False, metadata={"block": "options"}
    )
    save: Optional[list[Steps]] = field(
        default=Factory(list),
        metadata={"block": "perioddata", "shape": "(nper,)"},
    )
    print: Optional[list[Steps]] = field(
        default=Factory(list),
        metadata={"block": "perioddata", "shape": "(nper,)"},
    )

    def __init__(
        self,
        model=None,
        name=None,
        path=None,
        budget_file=None,
        budget_csv_file=None,
        head_file=None,
        format=None,
        perioddata=None,
    ):
        super().__init__(name, path)
        init_tree(
            self,
            parent=model,
            budget_file=budget_file,
            budget_csv_file=budget_csv_file,
            head_file=head_file,
            format=format,
            perioddata=perioddata,
        )
