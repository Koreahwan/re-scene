"""Serialize local dataset publication with synchronous catalog readers."""
from functools import wraps
from threading import RLock

dataset_lock = RLock()


def synchronized(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        with dataset_lock:
            return func(*args, **kwargs)
    return wrapped
