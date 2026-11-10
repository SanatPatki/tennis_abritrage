"""Player-name normalization. See AGENTS.md §5."""

from __future__ import annotations

import re

from unidecode import unidecode

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_SPACE = re.compile(r"\s+")


def normalize(name: str) -> str:
    """unidecode -> lowercase -> strip punctuation -> collapse whitespace."""
    s = unidecode(name).lower()
    s = _PUNCT.sub(" ", s)
    return _SPACE.sub(" ", s).strip()


def name_keys(name: str) -> dict[str, str]:
    """Produce matching keys: full, last, last_first_initial.

    Hyphens are treated as spaces so 'auger-aliassime' == 'auger aliassime'.

    NOTE: assumes "First Last" token order. tennis-data.co.uk uses
    "Lastname F." — the linker must try both orientations (see AGENTS.md §5).
    """
    s = normalize(name).replace("-", " ")
    parts = s.split()
    if not parts:
        return {"full": "", "last": "", "last_first_initial": ""}
    last = parts[-1]
    first_initial = parts[0][0] if parts[0] else ""
    return {
        "full": " ".join(parts),
        "last": last,
        "last_first_initial": f"{last} {first_initial}".strip(),
    }


def load_aliases(path: str) -> dict[str, str]:
    """Load data/player_aliases.csv -> {alias: canonical_name}."""
    import csv

    aliases: dict[str, str] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            aliases[normalize(row["alias"])] = row["canonical_name"]
    return aliases
