import numpy as np
import pandas as pd
from pathlib import Path
from .constants import How
from flopy.datbase import DataType, DataListInterface


class MFList(DataListInterface):
    def __init__(self):
        self.x = None

    @classmethod
    def load(cls):
        pass