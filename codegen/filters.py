from enum import Enum
from keyword import kwlist
from pathlib import Path
from typing import Any, ForwardRef, List, Optional, Union, get_args, get_origin

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
    del dd["legacy_dfn"]
    del dd["legacy_meta"]
    remap(dd, enter=enter, visit=visit)
    return vars_


class Filters:
    def base(component_name: tuple[str, str]) -> str:
        """Base class from which the input context should inherit."""
        if component_name == ("sim", "nam"):
            return "MFSimulationBase"
        if component_name[1] is None:
            return "MFModel"
        return "MFPackage"

    def title(component_name: tuple[str, str]) -> str:
        """
        The input context's unique title. This is not
        identical to `f"{l}{r}` in some cases, but it
        remains unique. The title is substituted into
        the file name and class name.
        """
        if component_name == ("sim", "nam"):
            return "simulation"
        l, r = component_name
        if l is None:
            return r
        if r is None:
            return l
        if l == "sim":
            return r
        if l in ["sln", "exg"]:
            return r
        return l + r

    def package_abbr(component_name: tuple[str, str]) -> str:
        if component_name[0] in ["sim", "sln", "exg", None]:
            return component_name[1]
        return "".join(component_name)

    def description(component_name: tuple[str, str]) -> str:
        """A description of the input context."""
        l, r = component_name
        base = Filters.base(component_name)
        title = Filters.title(component_name).title()
        if base == "MFPackage":
            return f"Modflow{title} defines a {r.upper()} package."
        elif base == "MFModel":
            return f"Modflow{title} defines a {l.upper()} model."
        elif base == "MFSimulationBase":
            return (
                "MFSimulation is used to load, build, and/or save a MODFLOW 6 simulation."
                " A MFSimulation object must be created before creating any of the MODFLOW"
                " 6 model objects."
            )

    def prefix(component_name: tuple[str, str]) -> str:
        """The input context class name prefix, e.g. 'MF' or 'Modflow'."""
        base = Filters.base(component_name)
        return "MF" if base == "MFSimulationBase" else "Modflow"

    def dfn_file_name(component_name: tuple[str, str]) -> str:
        if component_name[0] == "exg":
            return f"{'-'.join(component_name)}.dfn"
        if tuple(component_name) in [
            (None, "mvr"),
            (None, "gnc"),
        ]:
            return f"gwf-{component_name[1]}.dfn"
        if tuple(component_name) in [(None, "mvt")]:
            return f"gwt-{component_name[1]}.dfn"
        return f"{component_name[0] or 'sim'}-{component_name[1]}.dfn"

    def parent(dfn: dict, component_name: tuple[str, str]) -> str:
        # TODO should be no longer needed when parents are explicit in dfns
        """The input context's parent context type, if it can have a parent."""
        subpkg = dfn.get("ref", None)
        if subpkg:
            return subpkg["parent"]
        if component_name == ("sim", "nam"):
            return None
        elif component_name[1] is None or component_name[0] in [None, "sim", "exg", "sln"]:
            return "simulation"
        return "model"

    def skip_init(component_name: tuple[str, str]) -> List[str]:
        """Variables to skip in input context's `__init__` method."""
        base = Filters.base(component_name)
        if base == "MFSimulationBase":
            return [
                "tdis6",
                "models",
                "exchanges",
                "mxiter",
                "solutiongroup",
            ]
        elif base == "MFModel":
            return ["packages"]
        else:
            # if component_name[1] == "nam":
            #     return ["export_netcdf", "nc_filerecord"]
            if component_name == ("utl", "ts"):
                return ["method", "interpolation_method_single", "sfac"]
            return []

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

    def default_value(var: dict) -> Any:
        _default = var.get("default", None)
        if _default is not None:
            return _default
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

    def init(dfn: dict, component_name: tuple[str, str]) -> List[str]:
        component_base = Filters.base(component_name)
        component_vars = _get_vars(dfn)

        def _statements() -> Optional[List[str]]:
            if component_base == "MFSimulationBase":

                def _should_set(var: dict) -> bool:
                    return var["name"] not in [
                        "tdis6",
                        "models",
                        "exchanges",
                        "mxiter",
                        "solutiongroup",
                    ]

                stmts = []
                refs = {}
                for var in component_vars.values():
                    name = var["name"]
                    if name in kwlist:
                        name = f"{name}_"

                    subpkg = var.get("ref", None)

                    if _should_set(var):
                        if name not in ["hpc_data"]:
                            stmts.append(f"self.name_file.{name}.set_data({name})")
                        if not subpkg:
                            stmts.append(f"self.{name} = self.name_file.{name}")

                    if subpkg and subpkg["key"] not in refs:
                        refs[subpkg["key"]] = subpkg
                        args = f"'{subpkg['abbr']}', {subpkg['param']}"
                        stmts.append(f"self.{subpkg['param']} = self._create_package({args})")
            elif component_base == "MFModel":

                def _should_set(var: dict) -> bool:
                    return var["name"] not in [
                        "packages",
                    ]

                stmts = []
                refs = {}
                for var in component_vars.values():
                    name = var["name"]
                    if name in kwlist:
                        name = f"{name}_"

                    if _should_set(var):
                        stmts.append(f"self.name_file.{name}.set_data({name})")
                        stmts.append(f"self.{name} = self.name_file.{name}")

                    subpkg = var.get("ref", None)
                    if subpkg and subpkg["key"] not in refs:
                        refs[subpkg["key"]] = subpkg
                        args = f"'{subpkg['abbr']}', {subpkg['param']}"
                        stmts.append(f"self.{subpkg['param']} = self._create_package({args})")
            elif component_base == "MFPackage":

                def _should_build(var: dict) -> bool:
                    subpkg = var.get("ref", None)
                    if subpkg and component_name != (None, "nam"):
                        return False
                    return var["name"] not in [
                        "simulation",
                        "model",
                        "package",
                        "parent_model",
                        "parent_package",
                        "parent_model_or_package",
                        "parent_file",
                        "modelname",
                        "model_nam_file",
                        "method",
                        "interpolation_method_single",
                        "sfac",
                        "output",
                    ]

                stmts = []
                refs = {}
                for var in component_vars.values():
                    name = var["name"]
                    if name in kwlist:
                        name = f"{name}_"

                    subpkg = var.get("ref", None)
                    if _should_build(var):
                        if subpkg and component_name == (None, "nam"):
                            stmts.append(
                                f"self.{'_' if subpkg else ''}{subpkg['key']} "
                                f"= self.build_mfdata('{subpkg['key']}', None)"
                            )
                        else:
                            _name = name[:-1] if name.endswith("_") else name
                            name = name.replace("-", "_")
                            stmts.append(
                                f"self.{'_' if subpkg else ''}{name} "
                                f"= self.build_mfdata('{_name}', {name})"
                            )

                    if subpkg and subpkg["key"] not in refs and component_name[1] != "nam":
                        refs[subpkg["key"]] = subpkg
                        stmts.append(
                            f"self._{subpkg['key']} = self.build_mfdata('{subpkg['key']}', None)"
                        )
                        args = (
                            f"'{subpkg['abbr']}', {subpkg['val']}, "
                            f"'{subpkg['param']}', self._{subpkg['key']}"
                        )
                        stmts.append(
                            f"self._{subpkg['abbr']}_package = self.build_child_package({args})"
                        )

            return stmts

        return list(filter(None, _statements()))

    @staticmethod
    def safe_name(v: str) -> str:
        """
        Make sure a string is safe to use as a variable name in Python code.
        If the string is a reserved keyword, add a trailing underscore to it.
        Also replace any hyphens with underscores.
        """
        return (f"{v}_" if v in kwlist else v).replace("-", "_")

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
        The incoming name consists of snake_case words.
        The output is CamelCase.
        """
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
            py_type = Path
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
