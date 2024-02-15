import datetime
from collections import deque
from functools import wraps
from time import time


class Throttle:
    def __init__(self, calls, interval):
        self.calls = calls
        self.interval = interval
        self.__call_times = deque([0.0], maxlen=calls+1)

    def __call__(self, _callable):
        @wraps(_callable)
        def wrapper(*args, **kwargs):
            self.__call_times.append(time())
            if self.__call_times[-1] - self.__call_times[0] < self.interval:
                raise ThrottlingError('Too many requests')
            return _callable(*args, **kwargs)
        return wrapper


class ThrottlingError(Exception):
    pass


def to_timestamp(dt):
    if not dt:
        return 0
    if isinstance(dt, str):
        if dt.lower() == "today":
            dt = datetime.datetime.combine(
                datetime.datetime.now().date(),
                datetime.time.min
            ).timestamp()
        else:
            dt = datetime.datetime.fromisoformat(dt)
    if isinstance(dt, datetime.datetime):
        dt = dt.timestamp()
    return int(dt)


def try_or_none(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except Exception:
        return None


def return_none(*args, **kwargs):
    return None
