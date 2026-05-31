"""Core transcription logic (FFmpeg check, Whisper, file output)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[float], None]

INTERVAL_SECONDS = 300  # 5 minutes — block size for chapter-style navigation


def _windows_ffmpeg_candidates() -> list[Path]:
    """Common FFmpeg install locations on Windows (e.g. winget without shell restart)."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return []

    winget_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if not winget_root.is_dir():
        return []

    candidates: list[Path] = []
    for package_dir in winget_root.glob("Gyan.FFmpeg_*"):
        candidates.extend(package_dir.glob("*/bin/ffmpeg.exe"))
    return candidates


def resolve_ffmpeg_path() -> Path | None:
    """Return FFmpeg executable path if found on PATH or in known install dirs."""
    ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    ffmpeg_on_path = shutil.which("ffmpeg")
    if ffmpeg_on_path:
        return Path(ffmpeg_on_path)

    if sys.platform == "win32":
        for candidate in _windows_ffmpeg_candidates():
            if candidate.is_file():
                return candidate

    return None


def check_ffmpeg() -> bool:
    """Return True when FFmpeg is available on PATH or in known install dirs."""
    return resolve_ffmpeg_path() is not None


def ensure_ffmpeg_on_path() -> None:
    """Add FFmpeg bin dir to PATH for the current process when needed."""
    ffmpeg_path = resolve_ffmpeg_path()
    if ffmpeg_path is None:
        return

    ffmpeg_bin = str(ffmpeg_path.parent)
    current_path = os.environ.get("PATH", "")
    if ffmpeg_bin.lower() not in current_path.lower():
        os.environ["PATH"] = f"{ffmpeg_bin}{os.pathsep}{current_path}"


def format_timestamp(seconds: float) -> str:
    """Convert seconds to [MM:SS] or [HH:MM:SS] for long videos."""
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    return f"[{minutes:02d}:{secs:02d}]"


def format_time_range(start_seconds: float, end_seconds: float) -> str:
    """Format an interval label for seeking in a video player."""
    start = format_timestamp(start_seconds).strip("[]")
    end = format_timestamp(end_seconds).strip("[]")
    return f"[{start} — {end}]"


def format_segments_with_timestamps(segments: list[dict]) -> str:
    """Build UI/file text with one timestamped line per Whisper segment."""
    lines: list[str] = []
    for segment in segments:
        text = segment.get("text", "").strip()
        if not text:
            continue
        timestamp = format_timestamp(segment.get("start", 0.0))
        lines.append(f"{timestamp} {text}")
    return "\n".join(lines)


def group_segments_by_interval(
    segments: list[dict],
    interval_seconds: int = INTERVAL_SECONDS,
) -> list[tuple[int, int, list[dict]]]:
    """Group Whisper segments into fixed time blocks (default 5 min)."""
    if not segments:
        return []

    max_end = max(segment.get("end", 0.0) for segment in segments)
    blocks: list[tuple[int, int, list[dict]]] = []

    block_start = 0
    while block_start <= max_end:
        block_end = block_start + interval_seconds
        block_segments = [
            segment
            for segment in segments
            if block_start <= segment.get("start", 0.0) < block_end
        ]
        if block_segments:
            blocks.append((block_start, block_end, block_segments))
        block_start += interval_seconds

    return blocks


def format_segments_by_interval(
    segments: list[dict],
    interval_seconds: int = INTERVAL_SECONDS,
) -> str:
    """Build chapter-style text grouped by 5-minute blocks for video navigation."""
    blocks = group_segments_by_interval(segments, interval_seconds)
    if not blocks:
        return ""

    parts: list[str] = []
    separator = "=" * 72

    for block_start, block_end, block_segments in blocks:
        range_label = format_time_range(block_start, block_end)
        parts.append(separator)
        parts.append(f"{range_label}  — seek video to this mark")
        parts.append(separator)
        parts.append("")

        for segment in block_segments:
            text = segment.get("text", "").strip()
            if not text:
                continue
            timestamp = format_timestamp(segment.get("start", 0.0))
            parts.append(f"{timestamp} {text}")

        summary_parts = [
            segment.get("text", "").strip()
            for segment in block_segments
            if segment.get("text", "").strip()
        ]
        if summary_parts:
            parts.append("")
            parts.append("--- Block text ---")
            parts.append(" ".join(summary_parts))
            parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def resolve_output_dir(video_path: Path, output_dir: Path | None) -> Path:
    """Return folder for output files; default is the source video directory."""
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    return video_path.parent


def build_output_path(video_path: Path, output_dir: Path | None = None) -> Path:
    """Return transcription path in the chosen output folder."""
    target_dir = resolve_output_dir(video_path, output_dir)
    return target_dir / f"{video_path.stem}_transcription.txt"


def build_chapters_output_path(video_path: Path, output_dir: Path | None = None) -> Path:
    """Return 5-minute chapter file path in the chosen output folder."""
    target_dir = resolve_output_dir(video_path, output_dir)
    return target_dir / f"{video_path.stem}_by_5min.txt"


def build_log_output_path(video_path: Path, output_dir: Path | None = None) -> Path:
    """Return session log file path in the chosen output folder."""
    target_dir = resolve_output_dir(video_path, output_dir)
    return target_dir / f"{video_path.stem}_log.txt"


def save_transcription(output_path: Path, content: str) -> None:
    """Persist transcription text as UTF-8."""
    output_path.write_text(content, encoding="utf-8")


def get_whisper_audio_source(video_path: Path, log: LogCallback) -> Path:
    """
    Extract Whisper input audio to a temp WAV file.

    This keeps the original MP4 unlocked so the video player can work
    during transcription.
    """
    ffmpeg_path = resolve_ffmpeg_path()
    if ffmpeg_path is None:
        raise RuntimeError("FFmpeg not found.")

    temp_dir = Path(tempfile.gettempdir()) / "MeetScribe"
    temp_dir.mkdir(parents=True, exist_ok=True)
    cache_name = f"{video_path.stem}_{video_path.stat().st_mtime_ns}.wav"
    cached_audio = temp_dir / cache_name

    if cached_audio.is_file() and cached_audio.stat().st_size > 0:
        log("Using cached Whisper audio — video can play in parallel.")
        return cached_audio

    log("Extracting audio for Whisper — video can play in parallel...")
    temp_output = temp_dir / f"{video_path.stem}_{video_path.stat().st_mtime_ns}_work.wav"

    command = [
        str(ffmpeg_path),
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-f",
        "wav",
        str(temp_output),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        temp_output.unlink(missing_ok=True)
        details = (result.stderr or result.stdout or "Unknown FFmpeg error").strip()
        raise RuntimeError(f"Failed to extract audio: {details[-800:]}")

    if cached_audio.exists():
        cached_audio.unlink()
    temp_output.replace(cached_audio)
    log(f"Audio ready: {cached_audio.name}")
    return cached_audio


def transcribe_video(
    video_path: Path,
    model_name: str,
    log: LogCallback,
    set_progress: ProgressCallback,
    output_dir: Path | None = None,
) -> str:
    """
    Load Whisper model and transcribe the given video file.

    Whisper reads MP4 directly when FFmpeg is installed.
    """
    import whisper

    if not video_path.is_file():
        raise FileNotFoundError(f"File not found: {video_path}")

    if video_path.suffix.lower() != ".mp4":
        raise ValueError("Only MP4 files are supported.")

    set_progress(0.05)
    log("Checking FFmpeg...")
    if not check_ffmpeg():
        raise RuntimeError(
            "FFmpeg is not installed or not on PATH. "
            "Install FFmpeg and restart the application."
        )

    ensure_ffmpeg_on_path()
    ffmpeg_path = resolve_ffmpeg_path()
    log(f"FFmpeg found: {ffmpeg_path}")

    set_progress(0.15)
    log(f"Loading Whisper model '{model_name}'...")
    try:
        model = whisper.load_model(model_name)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load model '{model_name}'. "
            f"Try a smaller model if you run out of memory. Details: {exc}"
        ) from exc

    set_progress(0.25)
    audio_source = get_whisper_audio_source(video_path, log)

    set_progress(0.35)
    log("Transcription started. This may take a while...")

    try:
        result = model.transcribe(str(audio_source), verbose=False)
    except MemoryError as exc:
        raise MemoryError(
            f"Not enough memory for model '{model_name}'. "
            "Try a smaller model (tiny or base)."
        ) from exc
    except Exception as exc:
        error_text = str(exc).lower()
        if "cuda" in error_text and "out of memory" in error_text:
            raise MemoryError(
                f"Not enough GPU memory for model '{model_name}'. "
                "Try a smaller model or close other GPU applications."
            ) from exc
        if "invalid data" in error_text or "moov atom not found" in error_text:
            raise ValueError(
                "The video file is corrupted or was not fully downloaded."
            ) from exc
        raise RuntimeError(f"Transcription error: {exc}") from exc

    set_progress(0.85)
    segments = result.get("segments", [])
    formatted_text = format_segments_with_timestamps(segments)

    if not formatted_text.strip():
        formatted_text = result.get("text", "").strip()
        if not formatted_text:
            raise RuntimeError("Transcription returned empty text.")

    output_path = build_output_path(video_path, output_dir)
    log(f"Saving result: {output_path}")
    save_transcription(output_path, formatted_text)

    chapters_text = format_segments_by_interval(segments)
    if chapters_text.strip():
        chapters_path = build_chapters_output_path(video_path, output_dir)
        log(f"Saving 5-minute chapters: {chapters_path}")
        save_transcription(chapters_path, chapters_text)

    set_progress(1.0)
    log("Transcription completed successfully.")
    return formatted_text
