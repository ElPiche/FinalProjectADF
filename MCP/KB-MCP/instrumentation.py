# instrumentation.py - Lightweight instrumentation decorators for KB-MCP

import functools
import inspect
import time
from typing import Any, Callable

def timed(func: Callable) -> Callable:
    """
    Decorator that logs the execution time of a function.

    Args:
        func: Function to time

    Returns:
        Wrapped function that logs timing information
    """
    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000
                from utils import log_message
                log_message(
                    f"Function {func.__name__} completed",
                    "info",
                    func.__module__,
                    func.__name__,
                    duration_ms=duration_ms,
                )

        return async_wrapper

    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            from utils import log_message
            log_message(
                f"Function {func.__name__} completed",
                "info",
                func.__module__,
                func.__name__,
                duration_ms=duration_ms,
            )
    return wrapper


def watch_threshold(threshold_s: float):
    """
    Decorator that logs a warning if function execution exceeds threshold.

    Args:
        threshold_s: Threshold in seconds

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration_s = time.perf_counter() - start_time
                if duration_s > threshold_s:
                    from utils import log_message
                    log_message(f"Function {func.__name__} exceeded threshold: {duration_s:.2f}s > {threshold_s:.2f}s",
                               "warning", func.__module__, func.__name__, duration_ms=duration_s * 1000)
        return wrapper
    return decorator


def timeout_wrapper(func: Callable, timeout_s: float) -> Callable:
    """
    Wrap a function with a timeout using signal (Unix only) or threading.

    Note: This is a simple implementation. For production use, consider more robust solutions.

    Args:
        func: Function to wrap
        timeout_s: Timeout in seconds

    Returns:
        Wrapped function that raises TimeoutError on timeout
    """
    import signal
    import platform

    if platform.system() == 'Windows':
        # Windows doesn't support signal.SIGALRM, use threading instead
        import threading

        def wrapper(*args, **kwargs):
            result = [None]
            exception = [None]

            def target():
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:
                    exception[0] = e

            thread = threading.Thread(target=target)
            thread.start()
            thread.join(timeout_s)

            if thread.is_alive():
                raise TimeoutError(f"Function {func.__name__} timed out after {timeout_s} seconds")
            if exception[0]:
                raise exception[0]
            return result[0]

        return wrapper
    else:
        # Unix-like systems
        def wrapper(*args, **kwargs):
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Function {func.__name__} timed out after {timeout_s} seconds")

            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(timeout_s))
            try:
                return func(*args, **kwargs)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

        return wrapper