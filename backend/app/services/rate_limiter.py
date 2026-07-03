import time
import logging
from collections import defaultdict
from app.core.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self):
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> bool:
        now = time.time()
        window = 60.0
        max_reqs = settings.rate_limit_per_minute
        self._buckets[key] = [t for t in self._buckets[key] if now - t < window]
        if len(self._buckets[key]) >= max_reqs:
            logger.warning(f"Rate limit exceeded for {key}")
            return False
        self._buckets[key].append(now)
        return True


rate_limiter = RateLimiter()
