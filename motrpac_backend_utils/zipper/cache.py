#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center

import time
from collections import defaultdict
from multiprocessing import Array, Value
from typing import DefaultDict, List, Set, Type

from ..requester import Requester


class LastMessage:
    """
    A utility class for tracking the last message sent
    """

    def __init__(self, atomic_last_message_time: Type[Value]):
        self.time = atomic_last_message_time
        self.time.value = int(time.time())
        self.diff = 0

    def reset(self):
        self.time.value = int(time.time())

    def update_diff(self):
        self.diff = int(time.time()) - self.time.value
        return self.diff

    def __lt__(self, other: int):
        return self.diff < other

    def __gt__(self, other: int):
        return self.diff > other


class InProgressCache:
    """
    A utility class for tracking which files are being processed
    """

    def __init__(self, atomic_in_progress: Type[Value], atomic_processing_hashes: Type[Array]):
        """
        Creates a new instance of the InProgressCache
        """
        self.cache: DefaultDict[str, RequesterSet] = defaultdict()
        self.atomic_in_progress: Value = atomic_in_progress
        self.atomic_processing_hashes = atomic_processing_hashes

    def add_requester(self, file_hash: str, requester: Requester):
        """
        Adds a filehash to the cache if it does not exist, otherwise it will add the
        requester

        :param file_hash: The file to add
        :param requester: The requester of the file
        """
        if file_hash not in self.cache.keys():
            self.cache[file_hash] = RequesterSet(requester)
        else:
            self.cache[file_hash].add_requester(requester)
        self.update_progress()

    def finish_file(self, file_hash: str):
        """
        Signals the fileHash has been processed
        :param file_hash: The fileHash to signal as completed processing
        """
        self.cache[file_hash].finish()
        self.update_progress()

    def get_requesters(self, file_hash: str) -> List[Requester]:
        """
        Gets the requesters of a file

        :param file_hash: The set of files to get the requesters of
        """
        return self.cache[file_hash].get_requesters()

    def remove_requester(self, file_hash: str, requester: Requester):
        """
        Removes the requesters from the cache after the request to notify the requester
        has been made

        :param file_hash: The fileHash to remove the requesters of
        :param requester: The requester to remove
        """
        requester_set = self.cache[file_hash]
        if requester_set is not None:
            requester_set.remove_requester(requester)
        self.update_progress()

    def is_processed(self, file_hash: str) -> bool:
        """
        Gets whether the fileHash has been added to the cache

        :param file_hash: The file hash to check
        :return: Whether the hash is in the cache
        """
        return file_hash in self.cache.keys()

    def file_is_in_progress(self, file_hash: str) -> bool:
        """
        Gets whether the file processing for a particular file hash is in progress

        :param file_hash: The file hash to check
        :return: Whether the file processing is in progress
        """
        return self.is_processed(file_hash) and self.cache[file_hash].is_in_progress()

    def update_progress(self):
        """
        Gets whether any files are being processed, and updates the atomic values, which
        are shared across processes and used to determine if the program should continue
        to run
        """
        is_in_progress = False
        tmp_in_progress = []

        for f_hash, cache in self.cache.items():
            if cache.is_in_progress():
                is_in_progress = True
                tmp_in_progress.append(f_hash)

        # Set the atomic boolean
        self.atomic_in_progress.value = int(is_in_progress)

        # Set the atomic array
        self.atomic_processing_hashes.value = (",".join(tmp_in_progress)).encode()


class RequesterSet:
    """
    A utility class for tracking the requesters of the files being processed
    """

    requesters: Set[Requester]
    finished: bool

    def __init__(self, new_requester: Requester):
        """
        Creates a new instance of the RequesterSet with a new requester

        :param new_requester: The requester of the file
        """
        self.finished = False
        self.requesters = set()
        self.requesters.add(new_requester)

    def get_requesters(self) -> List[Requester]:
        """
        Gets a list of the requesters of the file

        :return: The list of requesters
        """
        return list(self.requesters)

    def add_requester(self, requester: Requester):
        """
        Adds a requester to the set

        :param requester: The requester to add
        """
        self.requesters.add(requester)

    def remove_requester(self, requester: Requester):
        """
        Remove requesters from the set

        :param requester: The requester to remove
        """
        self.requesters.remove(requester)
        if len(self.requesters) == 0:
            self.finished = True

    def is_in_progress(self) -> bool:
        """
        Gets whether the file processing is in progress

        :return: Whether the file processing is in progress
        """
        return not self.finished

    def resume(self):
        """
        Signals the file hash has not been processed
        """
        self.finished = False

    def finish(self):
        """
        Signals the file hash has been processed
        """
        self.finished = True
