import gc
import sys
import weakref
from typing import Any

import pytest

from pyinstrument.low_level.stat_profile import setstatprofile as setstatprofile_c

from .util import parametrize_setstatprofile


class CallCounter:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        self.count += 1


@parametrize_setstatprofile
def test_increment(setstatprofile):
    time = 0.0

    def fake_time():
        return time

    def fake_sleep(duration):
        nonlocal time
        time += duration

    counter = CallCounter()

    setstatprofile(counter, timer_func=fake_time, timer_type="timer_func")

    for _ in range(100):
        fake_sleep(1.0)

    setstatprofile(None)

    assert counter.count == 100


def test_invalid_timer_result_is_released():
    timer_result_ref = None

    class TimerResult:
        pass

    def invalid_timer():
        nonlocal timer_result_ref
        result = TimerResult()
        timer_result_ref = weakref.ref(result)
        return result

    with pytest.raises(RuntimeError, match="custom time function must return a float"):
        setstatprofile_c(
            CallCounter(),
            timer_func=invalid_timer,  # type: ignore[arg-type]
            timer_type="timer_func",
        )

    assert sys.getprofile() is None
    gc.collect()
    assert timer_result_ref is not None
    assert timer_result_ref() is None
