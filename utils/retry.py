import asyncio
import functools
import logging
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F")


def async_retry(max_attempts: int = 3, backoff_factor: int = 2) -> Callable:
    """
    Decorator: retries an async function up to max_attempts times.
    Waits backoff_factor**attempt seconds between tries (1s, 2s, 4s by default).
    Raises the last exception if all attempts fail.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_attempts - 1:
                        wait = backoff_factor ** attempt
                        logger.warning(
                            "%s failed (attempt %d/%d), retrying in %ds: %s",
                            func.__name__, attempt + 1, max_attempts, wait, exc,
                        )
                        await asyncio.sleep(wait)
            logger.error("%s failed after %d attempts", func.__name__, max_attempts)
            raise last_exc
        return wrapper
    return decorator
