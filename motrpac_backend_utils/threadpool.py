#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""
Threadpool utility functions.
"""
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from functools import wraps
from typing import TypeVar
from collections.abc import Callable

if sys.version_info >= (3, 10):
    from typing import ParamSpec
else:
    from typing_extensions import ParamSpec

P = ParamSpec("P")
R = TypeVar("R")
_DEFAULT_POOL = ThreadPoolExecutor()


def threadpool(
    pool: ThreadPoolExecutor | None = None,
) -> Callable[[Callable[P, R]], Callable[P, Future[R]]]:
    """
    Decorator that wraps a function and runs it in a threadpool.
    :param pool: A threadpool to use, or the default threadpool if None
    :return: The wrapped function.
    """

    def decorator(f: Callable[P, R]) -> Callable[P, Future[R]]:
        @wraps(f)
        def wrap(*args: P.args, **kwargs: P.kwargs) -> Future[R]:
            return (pool or _DEFAULT_POOL).submit(f, *args, **kwargs)

        return wrap

    return decorator
