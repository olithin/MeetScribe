"""
MeetScribe — desktop app for meeting video transcription (OpenAI Whisper).
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from clickable_text import insert_clickable_transcription
from transcription_service import (
    build_log_output_path,
    check_ffmpeg,
    save_transcription,
    transcribe_video,
)
from video_player import VideoPlayerPanel
from video_trim_service import export_clip, export_remove_end, export_remove_start

WHISPER_MODELS = ("tiny", "base", "small", "medium")
DEFAULT_MODEL = "small"


class TranscriptionApp(ctk.CTk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("MeetScribe — meeting video to text")
        self.geometry("1280x860")
        self.minsize(1040, 720)

        self._selected_file: Path | None = None
        self._output_dir: Path | None = None
        self._worker_thread: threading.Thread | None = None
        self._trim_thread: threading.Thread | None = None
        self._is_running = False
        self._is_trimming = False

        self._build_ui()
        self._log_startup_checks()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        header = ctk.CTkLabel(
            self,
            text="MeetScribe — meeting video to text",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        header.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        file_frame = ctk.CTkFrame(self)
        file_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        file_frame.grid_columnconfigure(1, weight=1)

        self.select_button = ctk.CTkButton(
            file_frame,
            text="Select MP4 file",
            command=self._on_select_file,
            width=160,
        )
        self.select_button.grid(row=0, column=0, padx=(12, 8), pady=12)

        self.file_path_var = tk.StringVar(value="No file selected")
        self.file_path_entry = ctk.CTkEntry(
            file_frame,
            textvariable=self.file_path_var,
            state="readonly",
        )
        self.file_path_entry.grid(row=0, column=1, padx=(0, 12), pady=12, sticky="ew")

        output_frame = ctk.CTkFrame(self)
        output_frame.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")
        output_frame.grid_columnconfigure(1, weight=1)

        self.output_dir_button = ctk.CTkButton(
            output_frame,
            text="Output folder",
            command=self._on_select_output_dir,
            width=160,
        )
        self.output_dir_button.grid(row=0, column=0, padx=(12, 8), pady=12)

        self.output_dir_var = tk.StringVar(value="Next to video (default)")
        self.output_dir_entry = ctk.CTkEntry(
            output_frame,
            textvariable=self.output_dir_var,
            state="readonly",
        )
        self.output_dir_entry.grid(row=0, column=1, padx=(0, 8), pady=12, sticky="ew")

        self.output_dir_reset_button = ctk.CTkButton(
            output_frame,
            text="Reset",
            command=self._on_reset_output_dir,
            width=90,
        )
        self.output_dir_reset_button.grid(row=0, column=2, padx=(0, 12), pady=12)

        options_frame = ctk.CTkFrame(self)
        options_frame.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="ew")

        model_label = ctk.CTkLabel(options_frame, text="Whisper model:")
        model_label.grid(row=0, column=0, padx=(12, 8), pady=12)

        self.model_combo = ctk.CTkComboBox(
            options_frame,
            values=list(WHISPER_MODELS),
            state="readonly",
            width=180,
        )
        self.model_combo.set(DEFAULT_MODEL)
        self.model_combo.grid(row=0, column=1, padx=(0, 12), pady=12, sticky="w")

        self.start_button = ctk.CTkButton(
            options_frame,
            text="Start transcription",
            command=self._on_start_transcription,
            width=200,
            height=36,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.start_button.grid(row=0, column=2, padx=(12, 12), pady=12)

        progress_frame = ctk.CTkFrame(self)
        progress_frame.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="ew")
        progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_label = ctk.CTkLabel(progress_frame, text="Progress: 0%")
        self.progress_label.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")

        self.progress_bar = ctk.CTkProgressBar(progress_frame)
        self.progress_bar.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        self.progress_bar.set(0.0)

        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.grid(row=5, column=0, padx=20, pady=(0, 20), sticky="nsew")
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_rowconfigure(0, weight=1)

        self._content_paned = tk.PanedWindow(
            content_frame,
            orient=tk.HORIZONTAL,
            sashwidth=6,
            sashrelief=tk.FLAT,
            opaqueresize=True,
            bg="#2a2a2a",
            bd=0,
            showhandle=False,
        )
        self._content_paned.grid(row=0, column=0, sticky="nsew")

        self.video_player = VideoPlayerPanel(
            self._content_paned,
            on_save_clip=self._on_save_clip,
            on_remove_start=self._on_remove_start,
            on_remove_end=self._on_remove_end,
        )
        self._content_paned.add(self.video_player, minsize=360, stretch="always")

        right_panel = ctk.CTkFrame(self._content_paned, fg_color="transparent")
        self._content_paned.add(right_panel, minsize=420, stretch="always")
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(1, weight=1)

        transcription_label = ctk.CTkLabel(
            right_panel,
            text="Transcription — click: seek | Shift+click: mark clip end:",
        )
        transcription_label.grid(row=0, column=0, padx=0, pady=(0, 4), sticky="w")

        self.transcription_textbox = ctk.CTkTextbox(right_panel, wrap="word", height=320)
        self.transcription_textbox.grid(row=1, column=0, pady=(0, 8), sticky="nsew")
        self._transcription_text = self.transcription_textbox._textbox

        log_label = ctk.CTkLabel(right_panel, text="Logs:")
        log_label.grid(row=2, column=0, padx=0, pady=(0, 4), sticky="w")

        self.log_textbox = ctk.CTkTextbox(right_panel, wrap="word", height=140)
        self.log_textbox.grid(row=3, column=0, sticky="ew")

        self.after(300, self._set_initial_pane_split)

    def _set_initial_pane_split(self) -> None:
        """Place divider between video and transcription (~42% for player)."""
        try:
            self.update_idletasks()
            width = self._content_paned.winfo_width()
            if width > 800:
                self._content_paned.sash_place(0, int(width * 0.42), 0)
        except tk.TclError:
            pass

    def _resolve_save_dir(self) -> Path | None:
        return self._output_dir

    def _log_startup_checks(self) -> None:
        self._append_log("Application started.")
        if check_ffmpeg():
            self._append_log("FFmpeg detected.")
        else:
            self._append_log(
                "WARNING: FFmpeg not found. Transcription and video trim will not work."
            )

        if self.video_player.has_vlc:
            self._append_log("VLC detected — audio playback enabled.")
        else:
            self._append_log(
                "VLC not found — silent preview only. "
                "Install: winget install VideoLAN.VLC"
            )

    def _on_select_file(self) -> None:
        if self._is_running:
            return

        file_path = filedialog.askopenfilename(
            title="Select MP4 file",
            filetypes=[("MP4 video", "*.mp4"), ("All files", "*.*")],
        )
        if not file_path:
            return

        self._selected_file = Path(file_path)
        self.file_path_var.set(str(self._selected_file))
        self._append_log(f"Selected file: {self._selected_file}")
        self.video_player.load(self._selected_file)

    def _on_select_output_dir(self) -> None:
        if self._is_running:
            return

        folder_path = filedialog.askdirectory(title="Select folder for output files")
        if not folder_path:
            return

        self._output_dir = Path(folder_path)
        self.output_dir_var.set(str(self._output_dir))
        self._append_log(f"Output folder: {self._output_dir}")

    def _on_reset_output_dir(self) -> None:
        if self._is_running:
            return

        self._output_dir = None
        self.output_dir_var.set("Next to video (default)")
        self._append_log("Output folder: next to video")

    def _on_timestamp_click(self, seconds: float) -> None:
        self.video_player.seek_to(seconds)
        self.video_player.mark_trim_start(seconds)
        self._append_log(f"Playing from {_format_seek_label(seconds)}")

    def _on_timestamp_mark_end(self, seconds: float) -> None:
        self.video_player.seek_to(seconds)
        self.video_player.mark_trim_end(seconds)
        self._append_log(f"Clip end marked: {_format_seek_label(seconds)}")

    def _on_save_clip(self, start_seconds: float, end_seconds: float) -> None:
        self._start_trim_job(
            "clip",
            lambda: export_clip(
                self._selected_file,
                start_seconds,
                end_seconds,
                self._resolve_save_dir(),
                self._append_log_threadsafe,
            ),
        )

    def _on_remove_start(self, cut_before_seconds: float) -> None:
        duration = self.video_player.get_duration_seconds()
        self._start_trim_job(
            "remove_start",
            lambda: export_remove_start(
                self._selected_file,
                cut_before_seconds,
                duration,
                self._resolve_save_dir(),
                self._append_log_threadsafe,
            ),
        )

    def _on_remove_end(self, cut_after_seconds: float) -> None:
        self._start_trim_job(
            "remove_end",
            lambda: export_remove_end(
                self._selected_file,
                cut_after_seconds,
                self._resolve_save_dir(),
                self._append_log_threadsafe,
            ),
        )

    def _start_trim_job(self, action: str, worker_callable) -> None:
        if self._selected_file is None:
            messagebox.showwarning("No file", "Select an MP4 file first.")
            return
        if self._is_running:
            messagebox.showwarning("Busy", "Wait for transcription to finish.")
            return
        if self._is_trimming:
            messagebox.showwarning("Busy", "Video trim is already in progress.")
            return
        if not check_ffmpeg():
            messagebox.showerror("FFmpeg", "FFmpeg not found. Video trim is unavailable.")
            return

        self._set_trim_state(True)
        action_labels = {
            "clip": "Saving clip...",
            "remove_start": "Trimming start...",
            "remove_end": "Trimming end...",
        }
        self._append_log(action_labels.get(action, "Trimming video..."))

        def run() -> None:
            try:
                output_path = worker_callable()
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Done",
                        f"Video saved:\n{output_path}",
                    ),
                )
            except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
                self._append_log_threadsafe(f"TRIM ERROR: {exc}")
                self.after(0, lambda e=exc: messagebox.showerror("Trim error", str(e)))
            finally:
                self.after(0, lambda: self._set_trim_state(False))

        self._trim_thread = threading.Thread(target=run, daemon=True)
        self._trim_thread.start()

    def _set_trim_state(self, is_trimming: bool) -> None:
        self._is_trimming = is_trimming
        state = "disabled" if is_trimming else "normal"
        self.video_player.set_trim_buttons_state(state)

    def _on_start_transcription(self) -> None:
        if self._is_running:
            self._append_log("Transcription is already running.")
            return

        if self._selected_file is None:
            messagebox.showwarning("No file", "Select an MP4 file first.")
            return

        if not self._selected_file.is_file():
            messagebox.showerror("File error", "The selected file does not exist.")
            return

        model_name = self.model_combo.get().strip()
        if model_name not in WHISPER_MODELS:
            messagebox.showerror("Model error", "Select a valid Whisper model.")
            return

        self._set_running_state(True)
        self._reset_progress()
        self.log_textbox.delete("1.0", "end")
        self._clear_transcription_view()
        self._append_log(f"Starting transcription with model '{model_name}'...")

        self._worker_thread = threading.Thread(
            target=self._run_transcription_worker,
            args=(self._selected_file, model_name, self._output_dir),
            daemon=True,
        )
        self._worker_thread.start()

    def _run_transcription_worker(
        self,
        video_path: Path,
        model_name: str,
        output_dir: Path | None,
    ) -> None:
        try:
            result_text = transcribe_video(
                video_path=video_path,
                model_name=model_name,
                log=self._append_log_threadsafe,
                set_progress=self._set_progress_threadsafe,
                output_dir=output_dir,
            )
            self.after(0, lambda: self._show_result(result_text))
        except (FileNotFoundError, ValueError, RuntimeError, MemoryError) as exc:
            self._append_log_threadsafe(f"ERROR: {exc}")
            self.after(0, lambda e=exc: messagebox.showerror("Transcription error", str(e)))
        except Exception as exc:
            self._append_log_threadsafe(f"UNEXPECTED ERROR: {exc}")
            self.after(
                0,
                lambda e=exc: messagebox.showerror(
                    "Unexpected error",
                    f"An unexpected error occurred:\n{e}",
                ),
            )
        finally:
            self.after(0, lambda: self._save_session_log(video_path, output_dir))
            self.after(0, lambda: self._set_running_state(False))

    def _save_session_log(self, video_path: Path, output_dir: Path | None) -> None:
        log_path = build_log_output_path(video_path, output_dir)
        log_content = self.log_textbox.get("1.0", "end").strip()
        transcription_content = self.transcription_textbox.get("1.0", "end").strip()
        combined = log_content
        if transcription_content:
            combined += "\n\n--- Transcription ---\n" + transcription_content

        if not combined.strip():
            return

        try:
            save_transcription(log_path, combined + "\n")
            self._append_log(f"Saving log: {log_path}")
        except OSError as exc:
            self._append_log(f"Failed to save log: {exc}")

    def _show_result(self, text: str) -> None:
        self._append_log("Transcription complete. Click timestamps on the right to seek.")
        self.transcription_textbox.configure(state="normal")
        insert_clickable_transcription(
            self._transcription_text,
            text,
            self._on_timestamp_click,
            self._on_timestamp_mark_end,
        )
        self.transcription_textbox.see("end")

    def _clear_transcription_view(self) -> None:
        self._transcription_text.configure(state="normal")
        self._transcription_text.delete("1.0", "end")
        self._transcription_text.configure(state="disabled")

    def _set_running_state(self, is_running: bool) -> None:
        self._is_running = is_running
        state = "disabled" if is_running else "normal"
        self.select_button.configure(state=state)
        self.output_dir_button.configure(state=state)
        self.output_dir_reset_button.configure(state=state)
        self.start_button.configure(state=state)
        self.model_combo.configure(state="disabled" if is_running else "readonly")
        if not is_running and not self._is_trimming:
            self.video_player.set_trim_buttons_state("normal")

    def _reset_progress(self) -> None:
        self.progress_bar.set(0.0)
        self.progress_label.configure(text="Progress: 0%")

    def _append_log(self, message: str) -> None:
        self.log_textbox.insert("end", message + "\n")
        self.log_textbox.see("end")

    def _append_log_threadsafe(self, message: str) -> None:
        self.after(0, lambda: self._append_log(message))

    def _set_progress_threadsafe(self, value: float) -> None:
        clamped = max(0.0, min(1.0, value))
        self.after(0, lambda: self._apply_progress(clamped))

    def _apply_progress(self, value: float) -> None:
        self.progress_bar.set(value)
        percent = int(value * 100)
        self.progress_label.configure(text=f"Progress: {percent}%")

    def _on_close(self) -> None:
        self.video_player.stop()
        self.destroy()


def _format_seek_label(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def main() -> None:
    app = TranscriptionApp()
    app.mainloop()


if __name__ == "__main__":
    main()
