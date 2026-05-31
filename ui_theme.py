"""Theme palettes and appearance preference (dark / light)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SETTINGS_DIR = Path.home() / ".meetscribe"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"

APPEARANCE_DARK = "dark"
APPEARANCE_LIGHT = "light"


@dataclass(frozen=True)
class ThemePalette:
    """Colors for one appearance mode."""

    mode: str
    text_primary: str
    text_secondary: str
    text_heading: str
    text_muted: str
    textbox_bg: str
    textbox_border: str
    link_color: str
    link_hover: str
    paned_bg: str
    video_overlay_fg: str
    theater_chrome_bg: str


DARK_PALETTE = ThemePalette(
    mode=APPEARANCE_DARK,
    text_primary="#CBCBCB",
    text_secondary="#A3A3A3",
    text_heading="#D6D6D6",
    text_muted="#848484",
    textbox_bg="#242424",
    textbox_border="#3A3A3A",
    link_color="#6BAAEE",
    link_hover="#8EC0F5",
    paned_bg="#2A2A2A",
    video_overlay_fg="#888888",
    theater_chrome_bg="#1A1A1A",
)

LIGHT_PALETTE = ThemePalette(
    mode=APPEARANCE_LIGHT,
    text_primary="#2E2E2E",
    text_secondary="#505050",
    text_heading="#1A1A1A",
    text_muted="#707070",
    textbox_bg="#F4F4F4",
    textbox_border="#C8C8C8",
    link_color="#1565C0",
    link_hover="#0D47A1",
    paned_bg="#D8D8D8",
    video_overlay_fg="#666666",
    theater_chrome_bg="#EBEBEB",
)

_PALETTES = {
    APPEARANCE_DARK: DARK_PALETTE,
    APPEARANCE_LIGHT: LIGHT_PALETTE,
}

_current_mode = APPEARANCE_DARK


def normalize_appearance_mode(mode: str | None) -> str:
    """Return a supported appearance mode."""
    if mode == APPEARANCE_LIGHT:
        return APPEARANCE_LIGHT
    return APPEARANCE_DARK


def load_appearance_mode() -> str:
    """Read saved theme from ~/.meetscribe/settings.json."""
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return normalize_appearance_mode(data.get("appearance"))
    except (OSError, json.JSONDecodeError, TypeError, AttributeError):
        return APPEARANCE_DARK


def save_appearance_mode(mode: str) -> None:
    """Persist theme choice."""
    mode = normalize_appearance_mode(mode)
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        data: dict[str, str] = {}
        if SETTINGS_PATH.is_file():
            try:
                loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = {str(k): str(v) for k, v in loaded.items()}
            except (json.JSONDecodeError, TypeError):
                pass
        data["appearance"] = mode
        SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def set_current_mode(mode: str) -> ThemePalette:
    """Update active palette and return it."""
    global _current_mode
    _current_mode = normalize_appearance_mode(mode)
    return get_palette()


def get_palette(mode: str | None = None) -> ThemePalette:
    """Palette for mode, or the currently active one."""
    key = normalize_appearance_mode(mode) if mode is not None else _current_mode
    return _PALETTES[key]
