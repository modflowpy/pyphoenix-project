from enum import Enum
from keyword import kwlist
from os import PathLike
from typing import Any, ForwardRef, Optional, Union, get_args, get_origin

import numpy as np
from boltons.iterutils import default_enter, remap
from numpy.typing import NDArray


def _try_get_enum_value(v: Any) -> Any:
    """
    Get the enum's value if the object is an instance
    of an enumeration, otherwise return it unaltered.
    """
    return v.value if isinstance(v, Enum) else v


def _get_vars(d: dict) -> dict[str, dict]:
    vars_ = dict()

    def visit(p, k, v):
        if isinstance(v, dict) and "type" in v:
            vars_[k] = v
        return True

    def enter(p, k, v):
        if isinstance(v, dict) and "type" in v:
            return (v, False)
        return default_enter(p, k, v)

    dd = d.copy()
    remap(dd, enter=enter, visit=visit)
    return vars_


class Filters:
    @staticmethod
    def description(dfn: dict[str, Any]) -> str:
        """A description of the input context."""
        parent = dfn.get("parent", None)
        if parent == "sim":
            return f"Modflow{dfn['name'].title()} defines a {dfn['name']} model."
        elif parent is not None:
            return f"Modflow{dfn['name'].title()} defines a {dfn['name']} package."
        else:
            return (
                "MFSimulation is used to load, build, and/or save a MODFLOW 6 simulation."
                " A MFSimulation object must be created before creating any of the MODFLOW"
                " 6 model objects."
            )

    @staticmethod
    def children(var: dict) -> Optional[dict]:
        _type = var["type"]
        items = var.get("items", None)
        fields = var.get("fields", None)
        choices = var.get("choices", None)
        if items:
            assert _type == "recarray"
            return items
        if fields:
            assert _type == "record"
            return fields
        if choices:
            assert _type == "keystring"
            return choices
        return None

    @staticmethod
    def variables(dfn: dict) -> dict[str, dict]:
        return _get_vars(dfn)

    @staticmethod
    def attrs(dfn: dict) -> list[dict]:
        """
        Map the context's input variables to corresponding class attributes, where applicable.
        """
        component_vars = _get_vars(dfn)
        return list(component_vars.values())

    @staticmethod
    def safe_name(v: str) -> str:
        """
        Make sure a string is safe to use as a variable name in Python code.
        If the string is a reserved keyword, add a trailing underscore to it.
        Also replace any hyphens with underscores.
        """
        return (f"{v}_" if v in kwlist else v).replace("-", "_")

    @staticmethod
    def math(v: str) -> str:
        """Massage latex equations"""
        v = v.replace("$<$", "<")
        v = v.replace("$>$", ">")
        if "$" in v:
            descsplit = v.split("$")
            mylist = [
                i.replace("\\", "") + ":math:`" + j.replace("\\", "\\\\") + "`"
                for i, j in zip(descsplit[::2], descsplit[1::2])
            ]
            mylist.append(descsplit[-1].replace("\\", ""))
            v = "".join(mylist)
        else:
            v = v.replace("\\", "")
        return v

    @staticmethod
    def clean(v: str) -> str:
        """Clean description"""
        replace_pairs = [
            ("``", '"'),  # double quotes
            ("''", '"'),
            ("`", "'"),  # single quotes
            ("~", " "),  # non-breaking space
            (r"\mf", "MODFLOW 6"),
            (r"\citep{konikow2009}", "(Konikow et al., 2009)"),
            (r"\citep{hill1990preconditioned}", "(Hill, 1990)"),
            (r"\ref{table:ftype}", "in mf6io.pdf"),
            (r"\ref{table:gwf-obstypetable}", "in mf6io.pdf"),
        ]
        for s1, s2 in replace_pairs:
            if s1 in v:
                v = v.replace(s1, s2)
        return v

    def value(v: Any) -> str:
        """
        Format a value to appear in the RHS of an assignment or argument-
        passing expression: if it's an enum, get its value; if it's `str`,
        quote it.
        """
        v = _try_get_enum_value(v)
        if isinstance(v, str) and v[0] not in ["'", '"']:
            v = f"'{v}'"
        return v

    @staticmethod
    def type_str(attr: dict[str, Any]) -> str:
        py_type = Filters._python_type(attr)
        return Filters._type_to_string(py_type, docstring=False)

    @staticmethod
    def type_docstr(attr: dict[str, Any]) -> str:
        py_type = Filters._python_type(attr)
        return Filters._type_to_string(py_type, docstring=True)

    @staticmethod
    def has_optional_or_default(attr: dict[str, Any]) -> bool:
        """Check if the attribute has an optional type or a default value."""
        return attr.get("optional", False) or "default" in attr

    @staticmethod
    def class_name(name: str) -> str:
        """Convert a string to a valid Python class name.
        The incoming name consists of snake_case or hyphened words.
        The output is CamelCase.
        """
        # Replace hyphens with underscores
        name = name.replace("-", "_")
        # capitalize each word and join them
        return "".join(word.capitalize() for word in name.split("_"))

    @staticmethod
    def _python_type(attr: dict[str, Any]) -> type | ForwardRef:
        """
        Get the Python type of the attribute, e.g. int, str, float,
        list, dict, etc.
        """
        types: dict[str, type] = {
            "integer": int,
            "real": float,
            "double precision": float,
            "string": str,
            "keyword": bool,
            "recarray": dict,
        }

        # TODO: If it's a record with a filein or fileout, use PathLike.

        # options with a shape are lists
        if attr.get("shape", None) and attr["type"] == "string":
            py_type: Any = list[str]
        elif attr.get("shape", None) and attr["type"] in ["real", "double precision"]:
            py_type = NDArray[np.float64]
        elif attr.get("shape", None) and attr["type"] == "integer":
            py_type = NDArray[np.int64]
        elif attr["type"] == "record":
            py_type = ForwardRef(Filters.class_name(attr["name"]), is_argument=False, is_class=True)
        elif "file" in attr["name"]:
            py_type = PathLike
        else:
            py_type = types.get(attr["type"], Any)

        if attr.get("optional", False):
            py_type = Optional[py_type]

        return py_type

    @staticmethod
    def _type_to_string(t: type | ForwardRef, docstring: bool = False) -> str:
        """Convert a type to its string representation.

        Args:
            t: The type to convert
            docstring: If True, format for docstrings (use 'or', 'optional').
                       If False, format for code (use '|', '| None').
        """

        # Handle None type
        if t is type(None):
            return "None"

        if type(t) is ForwardRef:
            return t.__forward_arg__

        # Handle basic types with __name__
        if hasattr(t, "__name__") and not hasattr(t, "__origin__"):
            return t.__name__

        # Handle generic types and special forms
        origin = get_origin(t)
        args = get_args(t)

        if origin is None:
            # Fallback for types without origin
            return getattr(t, "__name__", str(t))

        # Handle Union types (including Optional)
        if origin is Union:
            if len(args) == 2 and type(None) in args:
                # This is Optional[T] which is Union[T, None]
                non_none_type = args[0] if args[1] is type(None) else args[1]
                non_none_str = Filters._type_to_string(non_none_type, docstring)
                if docstring:
                    return f"{non_none_str}, optional"
                else:
                    return f"{non_none_str} | None"
            else:
                # Regular Union
                arg_strs = [Filters._type_to_string(arg, docstring) for arg in args]
                if docstring:
                    return " or ".join(arg_strs)
                else:
                    return " | ".join(arg_strs)

        # Handle other generic types (list, dict, NDArray, etc.)
        if hasattr(origin, "__name__"):
            origin_name = origin.__name__
            if args:
                arg_strs = [Filters._type_to_string(arg, docstring) for arg in args]
                return f"{origin_name}[{', '.join(arg_strs)}]"
            return origin_name

        # Fallback
        return str(t)
