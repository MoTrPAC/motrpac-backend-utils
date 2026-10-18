from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from ctypes import c_char
from multiprocessing import Array, Value

import pytest

from motrpac_backend_utils.models import Requester
from motrpac_backend_utils.zipper.cache import InProgressCache, RequestAction, RequesterSet

FILE_HASH = "a" * 32
THREAD_COUNT = 8
ALICE = Requester(name="Alice", email="alice@example.com", id="1")
BOB = Requester(name="Bob", email="bob@example.com", id="2")


@pytest.fixture
def cache() -> InProgressCache:
    return InProgressCache(Value("I", 0), Array(c_char, 1024))


def test_removing_last_requester_does_not_finish_file(cache: InProgressCache) -> None:
    cache.add_requester(FILE_HASH, ALICE)

    cache.remove_requester(FILE_HASH, ALICE)

    assert not cache.file_is_finished(FILE_HASH)
    assert cache.file_is_in_progress(FILE_HASH)


def test_remove_requester_ignores_unknown_hash_and_requester(cache: InProgressCache) -> None:
    cache.remove_requester(FILE_HASH, ALICE)
    cache.add_requester(FILE_HASH, ALICE)
    cache.remove_requester(FILE_HASH, BOB)

    assert cache.get_requesters(FILE_HASH) == [ALICE]


def test_fail_file_clears_in_progress_and_keeps_requesters(cache: InProgressCache) -> None:
    cache.add_requester(FILE_HASH, ALICE)
    cache.add_requester(FILE_HASH, BOB)
    assert cache.atomic_in_progress.value == 1
    assert cache.atomic_processing_hashes.value.decode() == FILE_HASH

    cache.fail_file(FILE_HASH)

    assert not cache.file_is_in_progress(FILE_HASH)
    assert not cache.file_is_finished(FILE_HASH)
    assert cache.atomic_in_progress.value == 0
    assert cache.atomic_processing_hashes.value.decode() == ""
    assert set(cache.get_requesters(FILE_HASH)) == {ALICE, BOB}


def test_fail_file_on_unknown_hash_is_a_no_op(cache: InProgressCache) -> None:
    cache.fail_file(FILE_HASH)

    assert not cache.is_processed(FILE_HASH)
    assert cache.atomic_in_progress.value == 0


def test_adding_requester_to_failed_file_resumes_it(cache: InProgressCache) -> None:
    cache.add_requester(FILE_HASH, ALICE)
    cache.fail_file(FILE_HASH)

    cache.add_requester(FILE_HASH, ALICE)

    assert cache.file_is_in_progress(FILE_HASH)
    assert cache.atomic_in_progress.value == 1


def test_adding_requester_to_finished_file_keeps_it_finished(cache: InProgressCache) -> None:
    cache.add_requester(FILE_HASH, ALICE)
    cache.finish_file(FILE_HASH)

    cache.add_requester(FILE_HASH, BOB)

    assert cache.file_is_finished(FILE_HASH)
    assert cache.atomic_in_progress.value == 0


def test_register_request_actions(cache: InProgressCache) -> None:
    assert cache.register_request(FILE_HASH, ALICE) == RequestAction.PROCESS
    assert cache.register_request(FILE_HASH, BOB) == RequestAction.WAIT

    cache.fail_file(FILE_HASH)
    assert cache.register_request(FILE_HASH, ALICE) == RequestAction.PROCESS
    assert cache.file_is_in_progress(FILE_HASH)

    cache.finish_file(FILE_HASH)
    assert cache.register_request(FILE_HASH, BOB) == RequestAction.NOTIFY
    assert cache.file_is_finished(FILE_HASH)


def _register_concurrently(
    cache: InProgressCache,
    requesters: list[Requester],
) -> list[RequestAction]:
    barrier = threading.Barrier(len(requesters))

    def register(requester: Requester) -> RequestAction:
        barrier.wait()
        return cache.register_request(FILE_HASH, requester)

    with ThreadPoolExecutor(max_workers=len(requesters)) as pool:
        return list(pool.map(register, requesters))


@pytest.mark.parametrize("failed_first", [False, True])
def test_concurrent_requests_for_same_hash_start_processing_once(
    cache: InProgressCache,
    monkeypatch: pytest.MonkeyPatch,
    *,
    failed_first: bool,
) -> None:
    # widen the window between checking for the hash and starting it, so that without a
    # lock several threads would see the hash as new (or failed) and all start processing
    original_init = RequesterSet.__init__
    original_resume = RequesterSet.resume

    def slow_init(self: RequesterSet, requester: Requester) -> None:
        time.sleep(0.05)
        original_init(self, requester)

    def slow_resume(self: RequesterSet) -> None:
        time.sleep(0.05)
        original_resume(self)

    if failed_first:
        cache.register_request(FILE_HASH, ALICE)
        cache.fail_file(FILE_HASH)
    monkeypatch.setattr(RequesterSet, "__init__", slow_init)
    monkeypatch.setattr(RequesterSet, "resume", slow_resume)
    requesters = [
        Requester(name=f"User {i}", email=f"user{i}@example.com", id=str(i))
        for i in range(THREAD_COUNT)
    ]

    actions = _register_concurrently(cache, requesters)

    assert actions.count(RequestAction.PROCESS) == 1
    assert actions.count(RequestAction.WAIT) == THREAD_COUNT - 1
    assert set(requesters) <= set(cache.get_requesters(FILE_HASH))
    assert cache.atomic_in_progress.value == 1


def test_concurrent_updates_to_different_hashes(cache: InProgressCache) -> None:
    hashes = [f"{i:032x}" for i in range(200)]

    def churn(file_hash: str) -> None:
        cache.register_request(file_hash, ALICE)
        cache.remove_requester(file_hash, ALICE)
        cache.finish_file(file_hash)

    with ThreadPoolExecutor(max_workers=THREAD_COUNT) as pool:
        list(pool.map(churn, hashes))

    assert all(cache.file_is_finished(h) for h in hashes)
    assert cache.atomic_in_progress.value == 0
