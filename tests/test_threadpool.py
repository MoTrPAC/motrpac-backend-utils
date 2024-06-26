#  Copyright (c) 2023. Mihir Samdarshi/MoTrPAC Bioinformatics Center

import unittest
from concurrent.futures import ThreadPoolExecutor

from motrpac_backend_utils.threadpool import threadpool


# Example function to be decorated
@threadpool
def square(x: int) -> int:
    return x**2


class TestThreadpoolDecorator(unittest.TestCase):
    def test_threadpool_decorator(self) -> None:
        # Test using the default thread pool
        squared_num = square(5)
        assert squared_num.result() == 25

        # Test using a custom thread pool
        custom_pool = ThreadPoolExecutor(max_workers=2)

        @threadpool
        def re_square(x: int) -> int:
            return x**2

        squared_num = re_square(3)
        assert squared_num.result() == 9

        # Clean up the custom thread pool
        custom_pool.shutdown()


if __name__ == "__main__":
    unittest.main()
