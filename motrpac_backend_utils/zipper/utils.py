#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center

from collections import defaultdict
from typing import Any, List


def nested_dict() -> defaultdict:
    """
    Creates a default dictionary where each value is another default dictionary.
    """
    return defaultdict(nested_dict)


def default_to_regular(d: Any) -> dict:
    """
    Converts :class:`defaultdict` of :class:`defaultdict` to dict of dicts.
    """
    if isinstance(d, defaultdict):
        d = {k: default_to_regular(v) for k, v in d.items()}
    return d


def get_path_dict(paths: List[str]) -> dict:
    """
    Creates a dictionary of the paths in the list to a nested dictionary with paths
    :param paths: The list of paths to convert
    :return: A nested dictionary with paths
    """
    new_path_dict = nested_dict()
    for path in paths:
        parts = path.split('/')
        if parts:
            marcher = new_path_dict
            for key in parts[:-1]:
                marcher = marcher[key]
            marcher.setdefault("contents", []).append(parts[-1])
    return default_to_regular(new_path_dict)
