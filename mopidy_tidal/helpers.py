import datetime
import socket
from collections import deque
from functools import wraps
from time import time
from typing import Any, Type, List


class Throttle:
    def __init__(self, calls: int, interval: int):
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

class Catch:
    def __init__(self, *args: Type[Exception], default: Any = None):
        self.exceptions = args
        self.default = default

    def __call__(self, _callable):
        @wraps(_callable)
        def wrapper(*args, **kwargs):
            try:
                return _callable(*args, **kwargs)
            except self.exceptions:
                return self.default
        return wrapper


def to_timestamp(dt):
    if isinstance(dt, str):
        if dt.lower() == "today":
            dt = datetime.datetime(
                *datetime.date.today().timetuple()[:3]
            )
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

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    ip = '127.0.0.1'
    try:
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
    except Exception:
        pass
    finally:
        s.close()
    return ip
