"""Live executor — sends orders via clients/kalshi.py.

GATE: refuse to send any live order unless MODE=live AND env
I_UNDERSTAND_LIVE_TRADING=yes. Never change these defaults.
"""

from __future__ import annotations

import os


class LiveExecutor:
    def __init__(self, *args, **kwargs):
        if os.environ.get("MODE") != "live" or os.environ.get("I_UNDERSTAND_LIVE_TRADING") != "yes":
            raise PermissionError(
                "live trading disabled: requires MODE=live and I_UNDERSTAND_LIVE_TRADING=yes"
            )
        raise NotImplementedError("live executor not implemented yet")
