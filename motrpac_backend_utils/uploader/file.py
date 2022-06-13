#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center
import hashlib
from typing import Generator

from motrpac_backend_utils.uploader.constants import COMPOSE_MAX_PARTS, GCS_CHUNK_SIZE


class FilePart:
    """
    A class for representing a file part
    """

    def __init__(self, filename: str, part_num: int, part_size: int, part_start: int):
        """
        Creates a new instance of the FilePart
        :param filename: the name of the original file
        :param part_num: the part number
        :param part_size: the size of the part
        :param part_start: the start position of the part
        """
        self.part_num = part_num
        self.part_size = part_size
        self.part_start = part_start
        self.part_name = hashlib.blake2b(
            f"{filename}_{part_num}_{part_start}_{part_size}".encode()
        ).hexdigest()


def ceil_div(a: int, b: int):
    """
    Returns the ceiling of a/b. This is the opposite of floor division the "//" operator,
    __floordiv__().
    :param a: some integer
    :param b: some integer
    :return: some integer
    """
    return -(a // -b)


def split_file(filename: str, file_size: int) -> Generator[FilePart]:
    """
    Splits a file into parts, yields a generator of FilePart objects

    :param filename: the name of the original file
    :param file_size: the size of the file to split
    """
    if ceil_div(file_size, COMPOSE_MAX_PARTS) < GCS_CHUNK_SIZE:
        num_parts = ceil_div(file_size, GCS_CHUNK_SIZE)
    else:
        num_parts = COMPOSE_MAX_PARTS

    for part_num in range(num_parts):
        if part_num == num_parts - 1:
            part_size = file_size - part_num * GCS_CHUNK_SIZE
        else:
            part_size = GCS_CHUNK_SIZE

        part_start = part_num * GCS_CHUNK_SIZE
        yield FilePart(filename, part_num, part_size, part_start)
