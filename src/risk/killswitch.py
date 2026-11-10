"""Kill switch. See AGENTS.md §9.

Triggers: any risk-limit breach, reconciliation mismatch, 3 consecutive order
errors, WS book desync not recovered within 60 s, clock skew > 2 s.

Action: DELETE every resting order, write /tmp/KILL lock file, send alert,
refuse new orders until a human removes the lock file.
"""

from __future__ import annotations

import os

LOCK_PATH = "/tmp/KILL"


def is_locked() -> bool:
    return os.path.exists(LOCK_PATH)


class KillSwitch:
    """TODO: wire cancel-all + Discord alert + lock file."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError
