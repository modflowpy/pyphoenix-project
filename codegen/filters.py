import builtins
import keyword
import os
from enum import Enum
from os import PathLike
from typing import Any, ForwardRef, Literal, Optional, Union, cast, get_args, get_origin

import jinja2
import numpy as np
from boltons.iterutils import remap
from modflow_devtools.dfn import get_fields
from numpy.typing import NDArray


def _try_get_enum_value(v: Any) -> Any:
    """
    Get the enum's value if the object is an instance
    of an enumeration, otherwise return it unaltered.
    """
    return v.value if isinstance(v, Enum) else v


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
    }

    # options with a shape are lists
    if attr.get("shape", None) and attr["type"] == "string":
        py_type: Any = NDArray[np.object_]
    elif attr.get("shape", None) and attr["type"] in ["real", "double precision"]:
        py_type = NDArray[np.float64]
    elif attr.get("shape", None) and attr["type"] == "integer":
        py_type = NDArray[np.int64]
    elif attr["type"] == "record":
        if any(field in attr["children"] for field in ["filein", "fileout"]):
            py_type = os.PathLike
        else:
            py_type = ForwardRef(Filters.class_name(attr["name"]), is_argument=False, is_class=True)
    elif "file" in attr["name"]:
        py_type = PathLike
    else:
        # TODO: Error on unknown type
        py_type = types.get(attr["type"], Any)

    if attr.get("optional", False):
        py_type = Optional[py_type]

    return py_type


def _type_to_string(
    t: type | ForwardRef,
    *,
    type_sep: Literal["|", "or"],
    optional: Literal[", optional", "| None"],
) -> str:
    """Convert a type to its string representation.

    Args:
        t: The type to convert
        type_sep: The separator to use for multiple types (either '|' or 'or')
        optional: The string to append for optional types (either '| None' or ', optional')
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
            non_none_str = _type_to_string(non_none_type, type_sep=type_sep, optional=optional)
            return f"{non_none_str}{optional}"
        else:
            # Regular Union
            arg_strs = [_type_to_string(arg, type_sep=type_sep, optional=optional) for arg in args]
            return f" {type_sep} ".join(arg_strs)

    if origin is np.ndarray:
        if args:
            if len(args) >= 2:
                # Extract the dtype from the second argument
                dtype_arg = args[1].__args__[0]
            else:
                dtype_arg = args[0].__args__[0]
            dtype_str = _type_to_string(dtype_arg, type_sep=type_sep, optional=optional)
            return f"NDArray[np.{dtype_str}]"
        return "NDArray"

    # Handle other generic types (list, dict, NDArray, etc.)
    if hasattr(origin, "__name__"):
        origin_name = origin.__name__
        if args:
            arg_strs = [_type_to_string(arg, type_sep=type_sep, optional=optional) for arg in args]
            return f"{origin_name}[{', '.join(arg_strs)}]"
        return origin_name

    # Fallback
    return str(t)


class Filters:
    @staticmethod
    def attrs(dfn: dict) -> list[dict]:
        """
        Map the context's input variables to corresponding class attributes, where applicable.
        """
        return list(get_fields(dfn).values())

    @staticmethod
    def safe_name(v: str) -> str:
        """
        Make sure a string is safe to use as a variable name in Python code.
        If the string is a reserved keyword, add a trailing underscore to it.
        Also replace any hyphens with underscores.
        """
        return (f"{v}_" if keyword.iskeyword(v) or v in dir(builtins) else v).replace("-", "_")

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

    @staticmethod
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
        py_type = _python_type(attr)
        return _type_to_string(py_type, type_sep="|", optional="| None")

    @staticmethod
    def type_docstr(attr: dict[str, Any]) -> str:
        py_type = _python_type(attr)
        return _type_to_string(py_type, type_sep="or", optional=", optional")

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
    @jinja2.pass_environment
    def children(env: jinja2.Environment, dfn: dict[str, Any]) -> list[dict[str, Any]]:
        result = []

        def visit(_, k, v):
            if isinstance(v, dict) and v.get("parent", None) == dfn["name"]:
                result.append(v)
            return True

        tree = cast(dict, env.globals["dfn_tree"]).copy()
        remap(tree, visit=visit)
        return result

    @staticmethod
    def double_quote(str: str) -> str:
        return f'"{str}"'
