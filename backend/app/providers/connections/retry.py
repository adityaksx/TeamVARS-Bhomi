import asyncio
import random
from typing import Callable, TypeVar, Coroutine, Any
import httpx
from .errors import ProviderError, ProviderErrorCode

T = TypeVar("T")

TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def is_transient_http_status(status_code: int) -> bool:
    return status_code in TRANSIENT_STATUS_CODES


async def execute_with_retry(
    operation: Callable[[], Coroutine[Any, Any, T]],
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    jitter: float = 0.25,
) -> tuple[T, int]:
    """Execute an async operation with bounded retry for transient errors.

    Returns:
        tuple[T, int]: The result and the number of attempts made.
    """
    attempt = 0
    last_exception = None

    while attempt < max_attempts:
        attempt += 1
        try:
            result = await operation()
            return result, attempt
        except ProviderError as exc:
            last_exception = exc
            if not exc.retryable or attempt >= max_attempts:
                raise
            delay = initial_delay * (backoff_factor ** (attempt - 1))
            jitter_amount = delay * jitter * random.uniform(-1, 1)
            sleep_time = max(0.2, delay + jitter_amount)
            await asyncio.sleep(sleep_time)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exception = exc
            if attempt >= max_attempts:
                raise
            delay = initial_delay * (backoff_factor ** (attempt - 1))
            jitter_amount = delay * jitter * random.uniform(-1, 1)
            sleep_time = max(0.2, delay + jitter_amount)
            await asyncio.sleep(sleep_time)

    if last_exception:
        raise last_exception
    raise RuntimeError("Retry loop exhausted with no result.")
