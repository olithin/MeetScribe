"""Embedded video player: VLC with audio (preferred) or OpenCV preview fallback."""

from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path

import customtkinter as ctk


def _format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


PLAYBACK_SPEEDS: tuple[float, ...] = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
DEFAULT_PLAYBACK_SPEED = 1.0


def _speed_label(rate: float) -> str:
    return f"{rate:g}x"


def _find_vlc_directory() -> Path | None:
    """Return VLC install directory on Windows/macOS if present."""
    candidates: list[Path] = []

    if sys.platform == "win32":
        candidates.extend(
            (
                Path(r"C:\Program Files\VideoLAN\VLC"),
                Path(r"C:\Program Files (x86)\VideoLAN\VLC"),
            )
        )
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            winget_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
            if winget_root.is_dir():
                for package_dir in winget_root.glob("VideoLAN.VLC_*"):
                    for vlc_exe in package_dir.rglob("vlc.exe"):
                        candidates.append(vlc_exe.parent)
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/VLC.app/Contents/MacOS"))

    for directory in candidates:
        if (directory / "libvlc.dll").exists() or (directory / "libvlc.dylib").exists():
            return directory
        if (directory / "vlc.exe").exists() or (directory / "VLC").exists():
            return directory
    return None


def _configure_vlc_environment() -> Path | None:
    """Configure DLL/plugin paths before importing python-vlc."""
    vlc_dir = _find_vlc_directory()
    if vlc_dir is None:
        return None

    if sys.platform == "win32":
        os.add_dll_directory(str(vlc_dir))
        plugins = vlc_dir / "plugins"
        if plugins.is_dir():
            os.environ["VLC_PLUGIN_PATH"] = str(plugins)
    return vlc_dir


class VideoPlayerPanel(ctk.CTkFrame):
    """Side panel video player with seek support for timestamp navigation."""

    def __init__(self, master, **kwargs) -> None:
        self._on_save_clip = kwargs.pop("on_save_clip", None)
        self._on_remove_start = kwargs.pop("on_remove_start", None)
        self._on_remove_end = kwargs.pop("on_remove_end", None)

        super().__init__(master, **kwargs)

        self._video_path: Path | None = None
        self._duration_seconds = 0.0
        self._slider_updating = False
        self._poll_after_id: str | None = None

        self._vlc_instance = None
        self._vlc_player = None
        self._vlc_media = None
        self._using_vlc = False

        self._opencv_cap = None
        self._opencv_fps = 25.0
        self._opencv_playing = False
        self._opencv_after_id: str | None = None
        self._photo = None
        self._current_seconds = 0.0
        self._trim_start: float | None = None
        self._trim_end: float | None = None
        self._playback_rate = DEFAULT_PLAYBACK_SPEED
        self._popup_window: VideoTheaterWindow | None = None
        self._external_surface: tk.Frame | None = None
        self._configure_after_id: str | None = None
        self._theater_configure_after_id: str | None = None
        self._theater_play_button: ctk.CTkButton | None = None
        self._theater_time_label: ctk.CTkLabel | None = None
        self._theater_seek_slider: ctk.CTkSlider | None = None
        self._theater_speed_menu: ctk.CTkOptionMenu | None = None
        self._theater_slider_updating = False
        self._embedded_window_id: int | None = None
        self._embedded_surface_size: tuple[int, int] | None = None

        self._build_ui()
        self._try_init_vlc()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        title = ctk.CTkLabel(
            self,
            text="Meeting video",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        title.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="w")

        self._video_container = ctk.CTkFrame(self, fg_color="#101010", corner_radius=0)
        self._video_container.grid(row=1, column=0, padx=8, pady=4, sticky="nsew")
        self._video_container.grid_rowconfigure(0, weight=1)
        self._video_container.grid_columnconfigure(0, weight=1)

        self._video_surface = tk.Frame(self._video_container, bg="#101010")
        self._video_surface.grid(row=0, column=0, sticky="nsew")
        self._video_surface.bind("<Configure>", self._on_video_surface_configure)

        self._video_background = tk.Frame(self._video_surface, bg="#101010")
        self._video_background.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._opencv_label = tk.Label(
            self._video_surface,
            bg="#101010",
            fg="#888888",
            text="Select an MP4 file",
        )
        self._opencv_label.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._theater_placeholder = ctk.CTkFrame(self._video_container, fg_color="#151515", corner_radius=0)
        self._theater_placeholder.grid_rowconfigure(0, weight=1)
        self._theater_placeholder.grid_columnconfigure(0, weight=1)
        self._theater_placeholder_label = ctk.CTkLabel(
            self._theater_placeholder,
            text="Video is playing\nin a separate window (L)",
            text_color="#666666",
            justify="center",
        )
        self._theater_placeholder_label.grid(row=0, column=0)

        self._status_label = ctk.CTkLabel(
            self,
            text="Player not loaded",
            text_color="#AAAAAA",
            wraplength=400,
            justify="left",
        )
        self._status_label.grid(row=2, column=0, padx=8, pady=(0, 4), sticky="w")

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=3, column=0, padx=8, pady=(0, 8), sticky="ew")
        controls.grid_columnconfigure(1, weight=1)

        self._play_button = ctk.CTkButton(
            controls,
            text="▶",
            width=44,
            command=self.toggle_play,
        )
        self._play_button.grid(row=0, column=0, padx=(0, 8))

        self._time_label = ctk.CTkLabel(controls, text="00:00 / --:--")
        self._time_label.grid(row=0, column=2, padx=(8, 8))

        speed_values = [_speed_label(rate) for rate in PLAYBACK_SPEEDS]
        self._speed_menu = ctk.CTkOptionMenu(
            controls,
            values=speed_values,
            width=72,
            command=self._on_speed_selected,
        )
        self._speed_menu.set(_speed_label(DEFAULT_PLAYBACK_SPEED))
        self._speed_menu.grid(row=0, column=3, padx=(0, 8))

        self._theater_button = ctk.CTkButton(
            controls,
            text="L",
            width=36,
            height=28,
            command=self._open_theater_window,
        )
        self._theater_button.grid(row=0, column=4)

        self._seek_slider = ctk.CTkSlider(
            controls,
            from_=0,
            to=1000,
            number_of_steps=1000,
            command=self._on_slider_changed,
        )
        self._seek_slider.grid(row=1, column=0, columnspan=5, padx=0, pady=(8, 0), sticky="ew")
        self._seek_slider.set(0)

        trim_frame = ctk.CTkFrame(self)
        trim_frame.grid(row=4, column=0, padx=8, pady=(0, 8), sticky="ew")
        trim_frame.grid_columnconfigure(0, weight=1)

        trim_title = ctk.CTkLabel(
            trim_frame,
            text="Trim video",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        trim_title.grid(row=0, column=0, columnspan=2, padx=8, pady=(8, 4), sticky="w")

        self._trim_range_label = ctk.CTkLabel(
            trim_frame,
            text="Start: —   End: —",
            text_color="#AAAAAA",
            wraplength=400,
            justify="left",
        )
        self._trim_range_label.grid(row=1, column=0, columnspan=2, padx=8, pady=(0, 6), sticky="w")

        mark_row = ctk.CTkFrame(trim_frame, fg_color="transparent")
        mark_row.grid(row=2, column=0, columnspan=2, padx=8, pady=(0, 6), sticky="ew")
        mark_row.grid_columnconfigure((0, 1, 2), weight=1)

        self._mark_start_button = ctk.CTkButton(
            mark_row,
            text="Mark start",
            command=self.mark_trim_start,
            height=28,
        )
        self._mark_start_button.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self._mark_end_button = ctk.CTkButton(
            mark_row,
            text="Mark end",
            command=self.mark_trim_end,
            height=28,
        )
        self._mark_end_button.grid(row=0, column=1, padx=4, sticky="ew")

        self._reset_trim_button = ctk.CTkButton(
            mark_row,
            text="Reset",
            command=self.reset_trim_marks,
            height=28,
            width=70,
        )
        self._reset_trim_button.grid(row=0, column=2, padx=(4, 0))

        self._save_clip_button = ctk.CTkButton(
            trim_frame,
            text="Save clip",
            command=self._request_save_clip,
            height=30,
        )
        self._save_clip_button.grid(row=3, column=0, columnspan=2, padx=8, pady=(0, 4), sticky="ew")

        quick_row = ctk.CTkFrame(trim_frame, fg_color="transparent")
        quick_row.grid(row=4, column=0, columnspan=2, padx=8, pady=(0, 8), sticky="ew")
        quick_row.grid_columnconfigure((0, 1), weight=1)

        self._remove_start_button = ctk.CTkButton(
            quick_row,
            text="Remove start",
            command=self._request_remove_start,
            height=28,
        )
        self._remove_start_button.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self._remove_end_button = ctk.CTkButton(
            quick_row,
            text="Remove end",
            command=self._request_remove_end,
            height=28,
        )
        self._remove_end_button.grid(row=0, column=1, padx=(4, 0), sticky="ew")

    def get_current_seconds(self) -> float:
        """Return current playback position in seconds."""
        if self._using_vlc and self._vlc_player:
            current_ms = self._vlc_player.get_time()
            if current_ms >= 0:
                return current_ms / 1000.0
        return self._current_seconds

    def get_duration_seconds(self) -> float:
        return self._duration_seconds

    def mark_trim_start(self, seconds: float | None = None) -> None:
        value = self.get_current_seconds() if seconds is None else seconds
        self._trim_start = max(0.0, value)
        self._update_trim_label()

    def mark_trim_end(self, seconds: float | None = None) -> None:
        value = self.get_current_seconds() if seconds is None else seconds
        if self._duration_seconds > 0:
            value = min(value, self._duration_seconds)
        self._trim_end = max(0.0, value)
        self._update_trim_label()

    def reset_trim_marks(self) -> None:
        self._trim_start = None
        self._trim_end = None
        self._update_trim_label()

    def set_trim_buttons_state(self, state: str) -> None:
        for button in (
            self._mark_start_button,
            self._mark_end_button,
            self._reset_trim_button,
            self._save_clip_button,
            self._remove_start_button,
            self._remove_end_button,
        ):
            button.configure(state=state)

    def _update_trim_label(self) -> None:
        start_text = _format_time(self._trim_start) if self._trim_start is not None else "—"
        end_text = _format_time(self._trim_end) if self._trim_end is not None else "—"
        start_clean = start_text.strip("[]")
        end_clean = end_text.strip("[]")
        self._trim_range_label.configure(text=f"Start: {start_clean}   End: {end_clean}")

    def _request_save_clip(self) -> None:
        if self._on_save_clip is None:
            return
        if self._trim_start is None or self._trim_end is None:
            self._set_status("Mark both start and end of the clip.")
            return
        if self._trim_end <= self._trim_start:
            self._set_status("End must be after start.")
            return
        self._on_save_clip(self._trim_start, self._trim_end)

    def _request_remove_start(self) -> None:
        if self._on_remove_start is None:
            return
        cut_point = self._trim_start if self._trim_start is not None else self.get_current_seconds()
        self._on_remove_start(cut_point)

    def _request_remove_end(self) -> None:
        if self._on_remove_end is None:
            return
        cut_point = self._trim_end if self._trim_end is not None else self.get_current_seconds()
        self._on_remove_end(cut_point)

    def _set_status(self, message: str) -> None:
        self._status_label.configure(text=message)

    def _try_init_vlc(self) -> None:
        try:
            vlc_dir = _configure_vlc_environment()
            if vlc_dir is None:
                raise RuntimeError("VLC not installed")

            import vlc

            self._vlc_instance = vlc.Instance("--no-video-title-show", "--quiet")
            self._vlc_player = self._vlc_instance.media_player_new()
            self._using_vlc = True
            self._embed_vlc()
            self._set_status("VLC ready — audio playback enabled.")
        except Exception:
            self._using_vlc = False
            self._set_status(
                "VLC not found — silent preview only. "
                "Install: winget install VideoLAN.VLC"
            )

    @property
    def has_vlc(self) -> bool:
        return self._using_vlc

    def _embed_surface(self) -> tk.Frame:
        if self._external_surface is not None and self._external_surface.winfo_exists():
            return self._external_surface
        return self._video_surface

    def _cancel_inline_embed_timer(self) -> None:
        if self._configure_after_id:
            self.after_cancel(self._configure_after_id)
            self._configure_after_id = None

    def _set_inline_video_visible(self, visible: bool) -> None:
        if visible:
            self._theater_placeholder.grid_remove()
            self._video_container.grid()
            return
        self._theater_placeholder.grid(row=0, column=0, sticky="nsew")
        self._video_container.grid_remove()

    def _close_theater_window(self) -> None:
        if self._popup_window is not None and self._popup_window.winfo_exists():
            self._popup_window.close()

    def _open_theater_window(self) -> None:
        if self._video_path is None:
            self._set_status("Select an MP4 file first.")
            return
        if not self._using_vlc:
            self._set_status("Pop-out window requires VLC for audio.")
            return
        if self._popup_window is not None and self._popup_window.winfo_exists():
            self._popup_window.bring_to_front()
            return

        self._cancel_inline_embed_timer()
        self._popup_window = VideoTheaterWindow(self)
        self._set_status("Pop-out window — drag to resize or go fullscreen.")

    def _on_speed_selected(self, label: str) -> None:
        self.set_playback_rate(float(label.replace("x", "")))

    def set_playback_rate(self, rate: float) -> None:
        self._playback_rate = rate
        label = _speed_label(rate)
        self._speed_menu.set(label)
        if self._theater_speed_menu is not None:
            self._theater_speed_menu.set(label)
        if self._using_vlc and self._vlc_player:
            self._vlc_player.set_rate(rate)

    def register_theater_controls(
        self,
        play_button: ctk.CTkButton,
        time_label: ctk.CTkLabel,
        seek_slider: ctk.CTkSlider,
        speed_menu: ctk.CTkOptionMenu,
    ) -> None:
        self._theater_play_button = play_button
        self._theater_time_label = time_label
        self._theater_seek_slider = seek_slider
        self._theater_speed_menu = speed_menu
        self._sync_play_buttons(bool(self._vlc_player and self._vlc_player.is_playing()))
        speed_menu.set(_speed_label(self._playback_rate))
        self._update_time_label(self.get_current_seconds())

    def clear_theater_controls(self) -> None:
        self._theater_play_button = None
        self._theater_time_label = None
        self._theater_seek_slider = None
        self._theater_speed_menu = None

    def attach_external_surface(self, surface: tk.Frame) -> None:
        self._cancel_inline_embed_timer()
        self._external_surface = surface
        self._embedded_window_id = None
        self._embedded_surface_size = None
        self._set_inline_video_visible(False)
        self._switch_vlc_output(force=True)
        self._schedule_theater_reembed()

    def detach_external_surface(self) -> None:
        self._external_surface = None
        self._popup_window = None
        self._embedded_window_id = None
        self._embedded_surface_size = None
        self.clear_theater_controls()
        self._set_inline_video_visible(True)
        self._switch_vlc_output(force=True)
        if self._video_path is not None:
            self._set_status(f"Loaded: {self._video_path.name}")

    def _schedule_theater_reembed(self) -> None:
        def retry(attempt: int) -> None:
            if self._external_surface is None or not self._external_surface.winfo_exists():
                return
            self._embedded_window_id = None
            self._switch_vlc_output(force=True)
            if attempt < 2:
                self.after(250, lambda: retry(attempt + 1))

        self.after(120, lambda: retry(0))

    def _on_theater_surface_configure(self) -> None:
        if not self._using_vlc:
            return
        if self._theater_configure_after_id:
            self.after_cancel(self._theater_configure_after_id)
        self._theater_configure_after_id = self.after(120, self._embed_vlc)

    def _video_display_size(self) -> tuple[int, int]:
        width = max(self._video_surface.winfo_width(), 320)
        height = max(self._video_surface.winfo_height(), 180)
        return width, height

    def _on_video_surface_configure(self, _event: tk.Event) -> None:
        if not self._using_vlc or self._external_surface is not None:
            return
        if self._configure_after_id:
            self.after_cancel(self._configure_after_id)
        self._configure_after_id = self.after(120, self._embed_vlc)

    def _sync_play_buttons(self, is_playing: bool) -> None:
        text = "⏸" if is_playing else "▶"
        self._play_button.configure(text=text)
        if self._theater_play_button is not None:
            self._theater_play_button.configure(text=text)

    def _seek_to_slider_value(self, value: float) -> None:
        if self._duration_seconds <= 0:
            return
        target_seconds = (float(value) / 1000.0) * self._duration_seconds
        if self._using_vlc and self._vlc_player:
            self._vlc_player.set_time(int(target_seconds * 1000))
        elif self._opencv_cap is not None:
            self._opencv_seek(target_seconds)
        self._update_time_label(target_seconds)

    def _embed_vlc(self) -> None:
        self._switch_vlc_output(force=False)

    def _apply_vlc_hwnd(self, window_id: int) -> None:
        if sys.platform == "win32":
            self._vlc_player.set_hwnd(window_id)
        elif sys.platform == "darwin":
            self._vlc_player.set_nsobject(window_id)
        else:
            self._vlc_player.set_xwindow(window_id)

    def _restore_vlc_time(self, current_ms: int) -> None:
        if not self._vlc_player or current_ms < 0:
            return
        self._vlc_player.set_time(current_ms)

    def _switch_vlc_output(self, *, force: bool) -> None:
        if not self._vlc_player:
            return

        surface = self._embed_surface()
        if self._external_surface is not None and surface is self._video_surface:
            return
        if not surface.winfo_exists():
            return

        surface.update_idletasks()
        width = surface.winfo_width()
        height = surface.winfo_height()
        if width < 32 or height < 32:
            self.after(80, lambda: self._switch_vlc_output(force=force))
            return

        window_id = surface.winfo_id()
        surface_size = (width, height)
        if (
            not force
            and window_id == self._embedded_window_id
            and surface_size == self._embedded_surface_size
        ):
            return

        was_playing = self._vlc_player.is_playing()
        current_ms = self._vlc_player.get_time()
        if current_ms < 0:
            current_ms = int(self._current_seconds * 1000)

        resume = was_playing or (force and self._external_surface is not None)
        if force and self._vlc_media is not None:
            self._vlc_player.stop()
            self._apply_vlc_hwnd(window_id)
            self._vlc_player.set_media(self._vlc_media)
        else:
            if was_playing:
                self._vlc_player.pause()
            self._apply_vlc_hwnd(window_id)

        self._embedded_window_id = window_id
        self._embedded_surface_size = surface_size

        if resume:
            self._vlc_player.play()
            self._vlc_player.set_rate(self._playback_rate)
            self.after(100, lambda ms=current_ms: self._restore_vlc_time(ms))
            self.after(300, lambda ms=current_ms: self._restore_vlc_time(ms))
            self._sync_play_buttons(True)
            self._start_poll()
        elif not self._vlc_player.is_playing():
            self._sync_play_buttons(False)

    def load(self, video_path: Path) -> None:
        """Load MP4 into the player."""
        self._close_theater_window()
        self.stop()
        self._video_path = video_path

        if self._using_vlc and self._vlc_player and self._vlc_instance:
            self._opencv_label.place_forget()

            media = self._vlc_instance.media_new(str(video_path))
            media.parse()
            self._vlc_media = media
            self._vlc_player.set_media(media)
            duration_ms = media.get_duration()
            self._duration_seconds = max(duration_ms / 1000.0, 0.0) if duration_ms > 0 else 0.0
            self._embed_vlc()
            self.set_playback_rate(self._playback_rate)
            self._set_status(f"Loaded: {video_path.name}")
            self.reset_trim_marks()
            self._update_time_label(0.0)
            return

        self._load_opencv(video_path)

    def seek_to(self, seconds: float) -> None:
        """Jump to timestamp and start playback."""
        if self._video_path is None:
            return

        if self._duration_seconds > 0:
            seconds = max(0.0, min(seconds, self._duration_seconds))

        if self._using_vlc and self._vlc_player:
            self._embed_vlc()
            self._vlc_player.play()
            self._vlc_player.set_rate(self._playback_rate)
            self._sync_play_buttons(True)
            self._start_poll()
            self._update_time_label(seconds)

            def apply_vlc_seek() -> None:
                if not self._vlc_player:
                    return
                self._vlc_player.set_time(int(seconds * 1000))
                if not self._vlc_player.is_playing():
                    self._vlc_player.play()
                    self._sync_play_buttons(True)
                self._update_time_label(seconds)

            self.after(120, apply_vlc_seek)
            return

        self._opencv_seek(seconds)
        self._opencv_playing = True
        self._sync_play_buttons(True)
        self._opencv_play_next_frame()

    def toggle_play(self) -> None:
        if self._video_path is None:
            return

        if self._using_vlc and self._vlc_player:
            if self._vlc_player.is_playing():
                self._vlc_player.pause()
                self._sync_play_buttons(False)
                self._stop_poll()
            else:
                self._vlc_player.play()
                self._vlc_player.set_rate(self._playback_rate)
                self._sync_play_buttons(True)
                self._start_poll()
            return

        if self._opencv_playing:
            self._opencv_playing = False
            self._sync_play_buttons(False)
            if self._opencv_after_id:
                self.after_cancel(self._opencv_after_id)
                self._opencv_after_id = None
        else:
            self._opencv_playing = True
            self._sync_play_buttons(True)
            self._opencv_play_next_frame()

    def stop(self) -> None:
        self._stop_poll()
        if self._opencv_after_id:
            self.after_cancel(self._opencv_after_id)
            self._opencv_after_id = None
        self._opencv_playing = False
        self._sync_play_buttons(False)

        if self._using_vlc and self._vlc_player:
            self._vlc_player.stop()

        if self._opencv_cap is not None:
            self._opencv_cap.release()
            self._opencv_cap = None

    def _ensure_opencv_label_visible(self) -> None:
        self._opencv_label.place(relx=0, rely=0, relwidth=1, relheight=1)

    def _load_opencv(self, video_path: Path) -> None:
        self._ensure_opencv_label_visible()
        import cv2

        self._opencv_cap = cv2.VideoCapture(str(video_path))
        if not self._opencv_cap.isOpened():
            self._set_status("Could not open video for preview.")
            return

        self._opencv_fps = self._opencv_cap.get(cv2.CAP_PROP_FPS) or 25.0
        frame_count = self._opencv_cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        self._duration_seconds = frame_count / self._opencv_fps if self._opencv_fps else 0.0
        self._opencv_show_frame(0)
        self.reset_trim_marks()
        self._set_status(f"Silent preview: {video_path.name}")

    def _opencv_reopen_capture(self) -> bool:
        import cv2

        if self._video_path is None:
            return False

        if self._opencv_cap is not None:
            self._opencv_cap.release()
            self._opencv_cap = None

        self._opencv_cap = cv2.VideoCapture(str(self._video_path))
        return self._opencv_cap.isOpened()

    def _opencv_show_frame(self, frame_index: int) -> None:
        import cv2
        from PIL import Image, ImageTk

        if self._opencv_cap is None and not self._opencv_reopen_capture():
            return

        self._opencv_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = self._opencv_cap.read()
        if not ok and self._opencv_reopen_capture():
            self._opencv_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = self._opencv_cap.read()
        if not ok:
            return

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame_rgb)
        image.thumbnail(self._video_display_size(), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(image)
        self._opencv_label.configure(image=self._photo, text="")

        current_seconds = frame_index / self._opencv_fps if self._opencv_fps else 0.0
        self._update_time_label(current_seconds)

    def _opencv_seek(self, seconds: float) -> None:
        if self._opencv_cap is None:
            return
        frame_index = int(seconds * self._opencv_fps)
        self._opencv_show_frame(frame_index)

    def _opencv_play_next_frame(self) -> None:
        if not self._opencv_playing or self._opencv_cap is None:
            return

        import cv2

        current_frame = int(self._opencv_cap.get(cv2.CAP_PROP_POS_FRAMES))
        next_frame = current_frame + 1
        total_frames = int(self._opencv_cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if next_frame >= total_frames:
            self._opencv_playing = False
            self._sync_play_buttons(False)
            return

        self._opencv_show_frame(next_frame)
        delay_ms = max(1, int(1000 / self._opencv_fps / self._playback_rate))
        self._opencv_after_id = self.after(delay_ms, self._opencv_play_next_frame)

    def _on_slider_changed(self, value: float) -> None:
        if self._slider_updating or self._duration_seconds <= 0:
            return
        self._seek_to_slider_value(value)

    def _on_theater_slider_changed(self, value: float) -> None:
        if self._theater_slider_updating or self._duration_seconds <= 0:
            return
        self._seek_to_slider_value(value)

    def _start_poll(self) -> None:
        self._stop_poll()
        self._poll_player()

    def _stop_poll(self) -> None:
        if self._poll_after_id:
            self.after_cancel(self._poll_after_id)
            self._poll_after_id = None

    def _poll_player(self) -> None:
        if self._using_vlc and self._vlc_player and self._vlc_player.is_playing():
            current_ms = self._vlc_player.get_time()
            if current_ms >= 0:
                self._update_time_label(current_ms / 1000.0)
        self._poll_after_id = self.after(200, self._poll_player)

    def _update_time_label(self, current_seconds: float) -> None:
        self._current_seconds = current_seconds
        duration = self._duration_seconds
        current_text = _format_time(current_seconds)
        duration_text = _format_time(duration) if duration > 0 else "--:--"
        time_text = f"{current_text} / {duration_text}"
        self._time_label.configure(text=time_text)
        if self._theater_time_label is not None:
            self._theater_time_label.configure(text=time_text)

        if duration <= 0:
            return

        slider_value = min(1000, max(0, int((current_seconds / duration) * 1000)))
        self._slider_updating = True
        self._seek_slider.set(slider_value)
        self._slider_updating = False
        if self._theater_seek_slider is not None:
            self._theater_slider_updating = True
            self._theater_seek_slider.set(slider_value)
            self._theater_slider_updating = False

    def destroy(self) -> None:
        self._close_theater_window()
        self.stop()
        super().destroy()


class VideoTheaterWindow(tk.Toplevel):
    """Pop-out resizable player window (seasonvar-style)."""

    def __init__(self, player: VideoPlayerPanel) -> None:
        super().__init__(player.winfo_toplevel())
        self._player = player
        self._fullscreen = False
        self.configure(bg="#1a1a1a")

        video_name = player._video_path.name if player._video_path else "MeetScribe"
        self.title(f"MeetScribe — {video_name}")

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = max(960, int(screen_w * 0.82))
        height = max(540, int(screen_h * 0.78))
        pos_x = max(0, (screen_w - width) // 2)
        pos_y = max(0, (screen_h - height) // 2 - 24)
        self.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
        self.minsize(640, 360)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._surface = tk.Frame(self, bg="#101010")
        self._surface.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))
        self._surface.bind("<Configure>", self._on_surface_configure)
        self._surface.bind("<Double-Button-1>", lambda _e: self.toggle_fullscreen())

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        controls.grid_columnconfigure(1, weight=1)

        self._play_button = ctk.CTkButton(
            controls,
            text="▶",
            width=44,
            command=player.toggle_play,
        )
        self._play_button.grid(row=0, column=0, padx=(0, 8))

        self._time_label = ctk.CTkLabel(controls, text="00:00 / --:--")
        self._time_label.grid(row=0, column=2, padx=(8, 8))

        speed_values = [_speed_label(rate) for rate in PLAYBACK_SPEEDS]
        self._speed_menu = ctk.CTkOptionMenu(
            controls,
            values=speed_values,
            width=72,
            command=player._on_speed_selected,
        )
        self._speed_menu.set(_speed_label(player._playback_rate))
        self._speed_menu.grid(row=0, column=3, padx=(0, 8))

        self._fullscreen_button = ctk.CTkButton(
            controls,
            text="⛶",
            width=36,
            height=28,
            command=self.toggle_fullscreen,
        )
        self._fullscreen_button.grid(row=0, column=4, padx=(0, 4))

        self._close_button = ctk.CTkButton(
            controls,
            text="✕",
            width=36,
            height=28,
            command=self.close,
        )
        self._close_button.grid(row=0, column=5)

        self._seek_slider = ctk.CTkSlider(
            controls,
            from_=0,
            to=1000,
            number_of_steps=1000,
            command=player._on_theater_slider_changed,
        )
        self._seek_slider.grid(row=1, column=0, columnspan=6, pady=(8, 0), sticky="ew")

        hint = ctk.CTkLabel(
            self,
            text="L — pop-out window | ⛶ — fullscreen | Esc — exit fullscreen",
            text_color="#888888",
        )
        hint.grid(row=2, column=0, padx=8, pady=(0, 8), sticky="w")

        self.transient(player.winfo_toplevel())
        self.bind("<Escape>", lambda _e: self._exit_fullscreen())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.update_idletasks()
        self.after_idle(self._attach_player)

    def _attach_player(self) -> None:
        if not self.winfo_exists():
            return

        self.update_idletasks()
        self.bring_to_front()
        self._surface.update_idletasks()

        if self._surface.winfo_width() < 32 or self._surface.winfo_height() < 32:
            self.after(50, self._attach_player)
            return

        self._player.register_theater_controls(
            self._play_button,
            self._time_label,
            self._seek_slider,
            self._speed_menu,
        )
        self._player.attach_external_surface(self._surface)

    def _on_surface_configure(self, _event: tk.Event) -> None:
        self._player._on_theater_surface_configure()

    def bring_to_front(self) -> None:
        if not self.winfo_exists():
            return
        self.update_idletasks()
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()
        self.after(400, self._release_topmost)

    def _release_topmost(self) -> None:
        if self.winfo_exists():
            self.attributes("-topmost", False)

    def toggle_fullscreen(self) -> None:
        if self._fullscreen:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self) -> None:
        if not self.winfo_exists():
            return
        self._fullscreen = True
        self.attributes("-fullscreen", True)
        self._fullscreen_button.configure(text="⛶")

    def _exit_fullscreen(self) -> None:
        if not self.winfo_exists() or not self._fullscreen:
            return
        self._fullscreen = False
        self.attributes("-fullscreen", False)
        self._fullscreen_button.configure(text="⛶")

    def close(self) -> None:
        self._exit_fullscreen()
        if self.winfo_exists():
            self._player.detach_external_surface()
            self.destroy()
