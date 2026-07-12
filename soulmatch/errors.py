"""Optional error alerting (V3-4-4). sentry-sdk is NOT in requirements.txt —
this only activates if both SENTRY_DSN is set AND the package happens to be
installed, so it can never break a deploy that doesn't want it.
"""

from __future__ import annotations

import logging

from . import config

log = logging.getLogger(__name__)

_initialized = False


def init_error_reporting() -> None:
    """Call once at app startup (see app.py). No-op unless SENTRY_DSN is set."""
    global _initialized
    if _initialized or not config.SENTRY_DSN:
        return
    try:
        import sentry_sdk
    except ImportError:
        log.warning(
            "SENTRY_DSN is set but sentry-sdk isn't installed — "
            "run `pip install sentry-sdk` to enable error reporting."
        )
        return
    sentry_sdk.init(dsn=config.SENTRY_DSN, traces_sample_rate=0.0)
    _initialized = True
