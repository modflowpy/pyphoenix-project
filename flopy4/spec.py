"""
Wrap `attrs` specification utilities.
"""

from collections.abc import Callable
from typing import Any

import attrs
from attrs import Attribute
from attrs import fields_dict as attrs_fields_dict


def fields_dict(cls) -> dict[str, Attribute]:
    """
    Return an ordered dictionary of fields for a component class,
    whose keys are field names. Each field is an `attrs.Attribute`.
    """
    return dict(attrs_fields_dict(cls))


def is_array(f: Attribute) -> bool:
    """Whether a field is an array (its DFN type, which the field functions
    in `flopy4.mf6.spec` record in its metadata)."""
    return f.metadata.get("type") == "array"


def reference_names(value):
    """A reference field's value as names, in the field's own shape (a
    list, or one value); names given as strings, and None, stay."""
    if isinstance(value, list):
        return [reference_names(v) for v in value]
    return value if value is None or isinstance(value, str) else value.name


def referenced(value) -> list:
    """The components a reference field's value refers to (not names)."""
    values = value if isinstance(value, list) else [value]
    return [v for v in values if v is not None and not isinstance(v, str)]


def resolve(value, candidates):
    """A reference field's value with each name replaced by the candidate
    of that name, looked up case-insensitively as MF6 does, in the field's
    own shape. Components, None and names matching no candidate stay."""
    if isinstance(value, list):
        return [resolve(v, candidates) for v in value]
    if not isinstance(value, str):
        return value
    return next((c for c in candidates if str(c.name).lower() == value.lower()), value)


def retarget(value, candidates):
    """A reference field's value with each component that isn't one of
    the candidates replaced by the candidate of its name, if there is one,
    in the field's own shape. Names, None and the candidates stay."""
    if isinstance(value, list):
        return [retarget(v, candidates) for v in value]
    if value is None or isinstance(value, str) or value.name is None:
        return value
    if any(c is value for c in candidates):
        return value
    found = resolve(str(value.name), candidates)
    return value if isinstance(found, str) else found


def _to_reference_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _check_reference(instance, attribute, value) -> None:
    if value is not None and not isinstance(value, str) and not hasattr(value, "name"):
        raise TypeError(f"{attribute.name} takes a component or a name, not {type(value).__name__}")


def reference(
    many: bool = True,
    check: "Callable[[Any, Any], str | None] | None" = None,
    required: bool = False,
):
    """Models this component refers to but doesn't own (e.g. the models a
    solution solves), given as objects or names: a list of them, or with
    `many=False` one (or None). The simulation owns its models; a
    reference never changes their parent or name, so names are looked up
    among the simulation's models when needed, not when the reference is
    made (see `resolve`). Shown and compared by name. A component given no
    parent joins its references' simulation (see
    `Component.__attrs_post_init__`).

    When written, a reference must be one of the simulation's models, and
    `check(component, model)`, if given, must return no problem with it. A
    single one must also be given if `required`."""
    shape: dict = (
        {"factory": list, "converter": _to_reference_list}
        if many
        else {"default": None, "validator": _check_reference}
    )
    return attrs.field(
        **shape,
        metadata={"reference": True, "check": check, "required": required},
        repr=lambda v: repr(reference_names(v)),
        eq=reference_names,
    )


def is_reference(f: Attribute) -> bool:
    """Whether a field refers to components it doesn't own (e.g. the models
    a solution solves). Such a field isn't a child field: walkers that
    follow children skip it, and its components keep their own parents."""
    return bool(f.metadata.get("reference"))
