"""Insert transcription text with clickable timestamp links."""

from __future__ import annotations

from collections.abc import Callable

import tkinter as tk

from timestamp_utils import TIMESTAMP_IN_BRACKETS, parse_timestamp_label
from ui_theme import get_palette


def _is_shift_click(event: tk.Event) -> bool:
    return bool(event.state & 0x0001)


def configure_read_only(text_widget: tk.Text) -> None:
    """Allow timestamp clicks while blocking manual text edits."""
    text_widget.configure(state="normal", cursor="")

    def block_edit(_event: tk.Event) -> str:
        return "break"

    text_widget.bind("<Key>", block_edit)
    text_widget.bind("<Control-v>", block_edit)
    text_widget.bind("<Button-2>", block_edit)
    text_widget.bind("<Button-3>", block_edit)


def insert_clickable_transcription(
    text_widget: tk.Text,
    content: str,
    on_seek: Callable[[float], None],
    on_mark_end: Callable[[float], None] | None = None,
    *,
    link_color: str | None = None,
    link_hover: str | None = None,
) -> None:
    """Fill a Text widget; timestamp tokens become clickable seek links."""
    palette = get_palette()
    link_fg = link_color or palette.link_color
    hover_fg = link_hover or palette.link_hover

    text_widget.configure(state="normal")
    text_widget.delete("1.0", "end")

    for line_index, line in enumerate(content.splitlines()):
        match = TIMESTAMP_IN_BRACKETS.search(line)
        if match is None:
            text_widget.insert("end", line + "\n")
            continue

        seconds = parse_timestamp_label(match.group(1))
        if seconds is None:
            text_widget.insert("end", line + "\n")
            continue

        before = line[: match.start()]
        token = line[match.start() : match.end()]
        after = line[match.end() :]

        if before:
            text_widget.insert("end", before)

        tag_name = f"seek_{line_index}_{int(seconds * 1000)}"
        text_widget.insert("end", token, (tag_name, "timestamp_link"))
        text_widget.insert("end", after + "\n")

        text_widget.tag_configure(tag_name, foreground=link_fg, underline=True)

        def on_click(event: tk.Event, seek_seconds: float = seconds) -> None:
            if on_mark_end is not None and _is_shift_click(event):
                on_mark_end(seek_seconds)
            else:
                on_seek(seek_seconds)
            return "break"

        text_widget.tag_bind(tag_name, "<Button-1>", on_click)

        def on_enter(_event: tk.Event, tag: str = tag_name) -> None:
            text_widget.configure(cursor="hand2")
            text_widget.tag_configure(tag, foreground=hover_fg)

        def on_leave(_event: tk.Event, tag: str = tag_name) -> None:
            text_widget.configure(cursor="")
            text_widget.tag_configure(tag, foreground=link_fg)

        text_widget.tag_bind(tag_name, "<Enter>", on_enter)
        text_widget.tag_bind(tag_name, "<Leave>", on_leave)

    configure_read_only(text_widget)
