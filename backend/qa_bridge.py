"""Pure, I/O-free helpers for the QA-bridge status endpoint: service-key header
parsing and a small fixed-window rate limiter with an injectable clock (so it's
deterministically testable). No DB, no scans, no network."""


def parse_service_key(authorization=None, x_api_key=None):
    """Extract the raw service token from either an `Authorization: Bearer …`
    header or an `X-Api-Key` header. Returns the token, or None if absent."""
    if authorization and authorization.lower().startswith("bearer "):
        tok = authorization[7:].strip()
        return tok or None
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    return None


class RateLimiter:
    """Fixed-window per-key limiter. `now` is passed in (seconds, monotonic-ish)
    so tests control time. Lenient by design — this blunts abuse on a read-only
    endpoint, it doesn't meter fair use."""

    def __init__(self, max_requests=120, window_s=60.0):
        self.max = max_requests
        self.window = window_s
        self._buckets = {}

    def allow(self, key, now):
        b = self._buckets.get(key)
        if not b or now - b[0] >= self.window:
            self._buckets[key] = [now, 1]
            return True
        if b[1] >= self.max:
            return False
        b[1] += 1
        return True
