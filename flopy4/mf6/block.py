import sys
from types import NoneType
from typing import Any, ClassVar, get_args, get_origin

import attrs

from flopy4.mf6.item import Item


@attrs.define(kw_only=True)
class Block:
    """One occurrence of a repeating block whose header is a record, e.g.
    OBS's ``BEGIN CONTINUOUS FILEOUT <file> [BINARY]``: the header record,
    then the block's own list."""

    # The header record's field name.
    _header: ClassVar[str]

    @classmethod
    def parts(cls) -> tuple[type[Item], str, type[Item]]:
        """The header's Item class, and the list's name and Item class."""
        attrs.resolve_types(cls, globalns=vars(sys.modules[cls.__module__]))
        fields = attrs.fields_dict(cls)
        header = fields[cls._header].type
        ((name, f),) = ((n, f) for n, f in fields.items() if n != cls._header)
        (item,) = get_args(f.type)
        assert isinstance(header, type) and issubclass(header, Item)
        assert isinstance(item, type) and issubclass(item, Item)
        return header, name, item

    def header_tokens(self) -> tuple:
        return getattr(self, self._header).to_tokens()


def block_list_type(field_type: Any) -> "type[Block] | None":
    """For Optional[list[B]] with B a Block, return B."""
    inner = next((a for a in get_args(field_type) if a is not NoneType), None)
    if get_origin(inner) is not list:
        return None
    (elem,) = get_args(inner)
    return elem if isinstance(elem, type) and issubclass(elem, Block) else None
