import pytest

from motrpac_backend_utils.threadpool import threadpool


# Example function to be decorated
@threadpool
def square(x: int) -> int:
    return x**2


def test_threadpool_decorator_default_pool() -> None:
    # Test using the default thread pool
    future = square(5)
    assert future.result() == 25  # noqa: PLR2004


@pytest.mark.parametrize(("val", "expected"), [(0, 0), (1, 1), (3, 9), (10, 100)])
def test_threadpool_decorator_parametrized(val: int, expected: int) -> None:
    # Ensure the decorator returns a future whose result matches
    future = square(val)
    assert future.result() == expected
