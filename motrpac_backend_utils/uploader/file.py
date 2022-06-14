#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center
import hashlib
import threading
from io import SEEK_SET
from typing import Generator, BinaryIO

from .constants import UPLOAD_BUFFER_SIZE


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


def split_file(filename: str, file_size: int) -> Generator[FilePart, None, None]:
    """
    Splits a file into parts, yields a generator of FilePart objects

    :param filename: the name of the original file
    :param file_size: the size of the file to split
    """
    # check if the number of parts is smaller than the chunk size
    num_parts = ceil_div(file_size, UPLOAD_BUFFER_SIZE)

    for part_num in range(num_parts):
        if part_num == num_parts - 1:
            part_size = file_size - part_num * UPLOAD_BUFFER_SIZE
        else:
            part_size = UPLOAD_BUFFER_SIZE

        part_start = part_num * UPLOAD_BUFFER_SIZE
        yield FilePart(filename, part_num, part_size, part_start)


class LockedFile:
    """
    A class for representing a file whose access is protected by a `threading.Lock`
    """

    def __init__(self, file_obj: BinaryIO):
        """
        Creates a new instance of the LockedFile
        :param file_obj: the file object
        """
        self.file_obj = file_obj
        self.lock = threading.Lock()

    def read(self, size: int) -> bytes:
        """
        Reads bytes from the file
        :param size: the number of bytes to read
        :return: the bytes read
        """
        with self.lock:
            return self.file_obj.read(size)

    def seek(self, offset: int, whence: int = SEEK_SET) -> int:
        """
        Seeks to a position in the file
        :param offset: the offset to seek to
        :param whence: the whence to seek from
        :return: the new position
        """
        with self.lock:
            return self.file_obj.seek(offset, whence)

    def tell(self) -> int:
        """
        Returns the current position in the file
        :return: the current position
        """
        with self.lock:
            return self.file_obj.tell()
