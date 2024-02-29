import numpy as np
from pathlib import Path
from .constants import How
from flopy.datbase import DataType, DataInterface


class MFArray(DataInterface):
    def __init__(self):
        self.x = None


    @classmethod
    def load(cls):
        pass