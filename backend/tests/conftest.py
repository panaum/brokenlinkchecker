import os
import sys

import pytest

# Make the backend/ package importable (dead_cta_detector, checker, models …)
# regardless of pytest's rootdir when run as `pytest tests/` from backend/.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(autouse=True)
def _reset_checker_domain_state():
    """Clear checker's per-domain throttling state between tests.

    The state is module-global by design: a long-lived server should remember
    that a domain is throttling it. In a test process that leaks across tests.
    Exception tests penalize "acme.test" up to PENALTY_MAX, and every later test
    that touches the same host then sleeps for it — which turned a 45-second
    suite into a 35-minute one.

    The lock/semaphore dicts are cleared for a second reason: each test drives
    its own event loop via asyncio.run(), and an asyncio primitive that has
    bound to a closed loop raises on reuse.
    """
    import checker

    for store in (
        checker._domain_penalty,
        checker._domain_last_request,
        checker._domain_locks,
        checker._domain_semaphores,
    ):
        store.clear()
    yield
    for store in (
        checker._domain_penalty,
        checker._domain_last_request,
        checker._domain_locks,
        checker._domain_semaphores,
    ):
        store.clear()
