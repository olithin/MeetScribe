"""Parse timestamp labels from transcription lines."""

from __future__ import annotations

import re

TIMESTAMP_IN_BRACKETS = re.compile(r"\[([^\]]+)\]")


def parse_timestamp_label(label: str) -> float | None:
    """Parse MM:SS, HH:MM:SS, or range start like 00:00 — 05:00."""
    cleaned = label.strip()
    for separator in ("—", "–", "-"):
        if separator in cleaned:
            cleaned = cleaned.split(separator, 1)[0].strip()
            break

    parts = cleaned.split(":")
    try:
        if len(parts) == 2:
            minutes, seconds = int(parts[0]), int(parts[1])
            return minutes * 60 + seconds
        if len(parts) == 3:
            hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
            return hours * 3600 + minutes * 60 + seconds
    except ValueError:
        return None
    return None


def extract_seek_seconds(line: str) -> float | None:
    """Return seek time from the first timestamp-like token in a line."""
    match = TIMESTAMP_IN_BRACKETS.search(line)
    if not match:
        return None
    return parse_timestamp_label(match.group(1))
