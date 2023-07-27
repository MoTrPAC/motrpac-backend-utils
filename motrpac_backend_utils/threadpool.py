#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""
Threadpool utility functions.
"""
from concurrent.futures import Future, ThreadPoolExecutor
from functools import wraps
from typing import TypeVar, ParamSpec
from collections.abc import Callable


P = ParamSpec("P")
R = TypeVar("R")
_DEFAULT_POOL = ThreadPoolExecutor()


def threadpool(wrapped_func: Callable[P, R]) -> Callable[P, Future[R]]:
    """
    Decorator that wraps a function and runs it in a threadpool.
    :return: The wrapped function.
    """

    def decorator(f: Callable[P, R]) -> Callable[P, Future[R]]:
        @wraps(f)
        def wrap(*args: P.args, **kwargs: P.kwargs) -> Future[R]:
            return _DEFAULT_POOL.submit(f, *args, **kwargs)

        return wrap

    return decorator(wrapped_func)
