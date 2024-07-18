from flopy.datbase import DataListInterface


class MFList(DataListInterface):
    def __init__(self):
        self.x = None

    @classmethod
    def load(cls):
        pass
