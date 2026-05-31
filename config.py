"""
MeetScribe user settings — edit paths here.

Obsidian: set OBSIDIAN_VAULT_PATH to your "Транскрипции" folder inside the vault.
When set, transcriptions are saved there unless you pick another folder in the GUI.
"""

from __future__ import annotations

from pathlib import Path

# Path to Obsidian "Транскрипции" folder; None = video folder / GUI output folder
OBSIDIAN_VAULT_PATH: Path | None = None
# Example:
# OBSIDIAN_VAULT_PATH = Path(r"D:\Obsidian\MyVault\Транскрипции")

# Saved transcription format: ".txt" or ".md"
OUTPUT_FILE_EXTENSION: str = ".md"

# Group Whisper segments into paragraphs (~30–60 s) for reading and LLM use
PARAGRAPH_TARGET_SECONDS: int = 45
PARAGRAPH_MAX_SECONDS: int = 60
