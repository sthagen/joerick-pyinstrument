import contextvars
import types
from typing import Any, Callable

from pyinstrument.low_level.types import TimerType

def setstatprofile(
    target: Callable[[types.FrameType, str, Any], Any] | None,
    interval: float = 0.001,
    context_var: contextvars.ContextVar[object | None] | None = None,
    timer_type: TimerType | None = None,
    timer_func: Callable[[], float] | None = None,
) -> None: ...
def get_frame_info(frame: types.FrameType) -> str: ...
