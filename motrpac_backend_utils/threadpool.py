#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""
Threadpool utility functions
"""
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from functools import wraps
from typing import Callable, Optional, TypeVar

if sys.version_info >= (3, 10):
    from typing import ParamSpec
else:
    from typing_extensions import ParamSpec

P = ParamSpec("P")
R = TypeVar("R")
_DEFAULT_POOL = ThreadPoolExecutor()


def threadpool(pool: Optional[ThreadPoolExecutor]):
    """
    Decorator that wraps a function and runs it in a threadpool.
    :param f: The function to wrap
    :param pool: A threadpool to use, or the default threadpool if None
    :return: The wrapped function
    """

    def decorator(f: Callable[P, R]) -> Callable[P, Future[R]]:
        @wraps(f)
        def wrap(*args, **kwargs) -> Future[R]:
            return (pool or _DEFAULT_POOL).submit(f, *args, **kwargs)

        return wrap

    return decorator
