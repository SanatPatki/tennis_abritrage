"""Kalshi market <-> odds fixture <-> results linker. See AGENTS.md §5 — the hardest part.

confidence >= 0.95 auto-links; 0.80-0.95 stored but flagged (no trading);
below ignored. Store mapping in match_links.
"""

from __future__ import annotations


class MatchLinker:
    """TODO:
    - candidate pairs: same tour, start times within +/-12h
    - score = best rapidfuzz.token_sort_ratio over the two players
      + tournament name similarity + time proximity
    - explicit player-orientation mapping (which Kalshi market YES = which
      odds outcome); unit-test with swapped orders
    """

    def __init__(self, *args, **kwargs):
        raise NotImplementedError
