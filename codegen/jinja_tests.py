from typing import Any


class Tests:
    @staticmethod
    def startswith(s: str, prefix: str) -> bool:
        """
        Check if string `s` starts with string `prefix`.
        """
        return s.startswith(prefix)

    @staticmethod
    def endswith(s: str, suffix: str) -> bool:
        """
        Check if string `s` ends with string `suffix`.
        """
        return s.endswith(suffix)

    @staticmethod
    def dis_or_tdis_package(dfn: dict[str, Any]) -> bool:
        name_split = dfn["name"].split("-")
        return len(name_split) > 1 and name_split[1] in ["dis", "tdis"]

    @staticmethod
    def dis_package(dfn: dict[str, Any]) -> bool:
        return dfn["name"].endswith("-dis")
