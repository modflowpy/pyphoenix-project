from typing import IO, TYPE_CHECKING, Any

from flopy4.mf6.codec.reader.parser import get_basic_parser, get_typed_parser
from flopy4.mf6.codec.reader.transformer import BasicTransformer, TypedTransformer

if TYPE_CHECKING:
    from flopy4.mf6.component import Component

BASIC_PARSER = get_basic_parser()
BASIC_TRANSFORMER = BasicTransformer()


def _get_grammar_name(component_type: type["Component"]) -> str:
    """Derive grammar file name from component type."""
    module = component_type.__module__
    class_name = component_type.__name__.lower()

    # Parse module path: flopy4.mf6.{model_type}.{package_name} or flopy4.mf6.{special}
    parts = module.split(".")

    if len(parts) >= 4 and parts[2] in ("gwf", "gwt", "gwe", "prt", "chf", "swf", "olf"):
        # Package: flopy4.mf6.gwf.dis -> gwf-dis
        model_type = parts[2]
        return f"{model_type}-{class_name}"
    elif len(parts) == 3 and parts[2] in ("gwf", "gwt", "gwe", "prt", "chf", "swf", "olf"):
        # Model: flopy4.mf6.gwf -> gwf-nam
        model_type = parts[2]
        return f"{model_type}-nam"
    elif "simulation" in module:
        # Simulation: flopy4.mf6.simulation -> sim-nam
        return "sim-nam"
    elif "tdis" in module:
        # TDIS: flopy4.mf6.tdis -> sim-tdis
        return "sim-tdis"
    elif "solution" in module or "ims" in class_name:
        # Solution: flopy4.mf6.solution -> sln-ims
        return "sln-ims"
    else:
        # Fallback to class name
        return class_name


def load(fp: IO[str], component_type: type["Component"] | None = None) -> Any:
    """
    Load and parse an MF6 input file.

    Parameters
    ----------
    fp : IO[str]
        File-like object containing MF6 input file content
    component_type : type[Component], optional
        Component class to use for typed parsing and transformation.
        If provided, uses typed parser and TypedTransformer.
        If None, uses basic parser and BasicTransformer.

    Returns
    -------
    Any
        Parsed MF6 input file structure
    """
    return loads(fp.read(), component_type=component_type)


def loads(data: str, component_type: type["Component"] | None = None) -> Any:
    """
    Parse MF6 input file content from string.

    Parameters
    ----------
    data : str
        MF6 input file content as string
    component_type : type[Component], optional
        Component class to use for typed parsing and transformation.
        If provided, uses typed parser and TypedTransformer.
        If None, uses basic parser and BasicTransformer.

    Returns
    -------
    Any
        Parsed MF6 input file structure
    """
    if component_type is not None:
        # Use typed parser and transformer for the specific component type
        try:
            grammar_name = _get_grammar_name(component_type)
            parser = get_typed_parser(grammar_name)
            transformer = TypedTransformer(component_type=component_type)
            tree = parser.parse(data)
            return transformer.transform(tree)
        except (FileNotFoundError, Exception) as e:
            # Fall back to basic parser if typed grammar doesn't exist or fails
            # This handles grammar errors, parse errors, etc.
            import warnings

            warnings.warn(
                f"Typed parsing failed for {component_type.__name__}, falling back to basic: {e}",
                UserWarning,
            )
            pass

    # Use basic parser and transformer
    tree = BASIC_PARSER.parse(data)
    return BASIC_TRANSFORMER.transform(tree)
