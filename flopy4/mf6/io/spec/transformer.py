from lark import Transformer

from flopy4.io.lark import parse_string


class DFNTransformer(Transformer):
    """
    Transforms a parse tree for the MODFLOW 6
    specification language into a nested AST
    suitable for generating an object model.

    Notes
    -----
    Rather than a flat list of parameters for each component,
    which a subsequent step is responsible for turning into a
    an object hierarchy, we derive the hierarchical parameter
    structure from the DFN file and return a dict of blocks,
    each of which is a dict of parameters.

    This can be fed to a Jinja template to generate component
    modules.
    """

    def key(self, k):
        (k,) = k
        return str(k).lower()

    def value(self, v):
        (v,) = v
        return str(v)

    def attribute(self, p):
        return str(p[0]), str(p[1])

    def parameter(self, p):
        return dict(p[1:])

    def paramname(self, n):
        (n,) = n
        return "name", str(n)

    def paramblock(self, b):
        (b,) = b
        return "block", str(b)

    def component(self, c):
        (c,) = c
        return "component", str(c)

    def subcompnt(self, s):
        (s,) = s
        return "subcomponent", str(s)

    def blockname(self, b):
        (b,) = b
        return "block", str(b)

    def block(self, b):
        params = {p["name"]: p for p in b[6:]}
        return b[4][1], params

    string = parse_string
    dfn = dict
