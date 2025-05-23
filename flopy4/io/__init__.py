"""
Core IO framework. Program interfaces can plug in bespoke
load/write methods for particular components and formats.

Most of this module is stolen/simplified from astropy, at:
- https://github.com/astropy/astropy/tree/main/astropy/io.
"""

from flopy4.io.framework import IOMethod, Loader, Writer
from flopy4.io.registry import DEFAULT_REGISTRY

__all__ = ["IOMethod", "Loader", "Writer", "DEFAULT_REGISTRY"]
