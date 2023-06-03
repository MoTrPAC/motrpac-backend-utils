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
    arg: ThreadPoolExecutor | Callable[P, R] | None = None,
    **kwargs: ThreadPoolExecutor,
) -> ThreadPoolExecutor | Callable[[Callable[P, R]], Callable[P, Future[R]]]:
    """
    Decorator that wraps a function and runs it in a threadpool.
    :param arg: A threadpool to use, or the default threadpool if None
    :return: The wrapped function.
    """
    # Check if decorator used without parentheses
    if callable(arg):
        # Call threadpool with default arguments and return the resulting decorator
        # noinspection PyTypeChecker
        return threadpool()(arg)

    pool = arg or kwargs.get("pool") or _DEFAULT_POOL

    def decorator(f: Callable[P, R]) -> Callable[P, Future[R]]:
        @wraps(f)
        def wrap(*args: P.args, **kwargs: P.kwargs) -> Future[R]:
            return pool.submit(f, *args, **kwargs)

        return wrap

    return decorator
