"""Video trimming and clip export via FFmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from transcription_service import LogCallback, ensure_ffmpeg_on_path, resolve_ffmpeg_path, resolve_output_dir


def _seconds_to_label(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}-{minutes:02d}-{secs:02d}"
    return f"{minutes:02d}-{secs:02d}"


def build_trim_output_path(
    video_path: Path,
    start_seconds: float,
    end_seconds: float,
    suffix: str,
    output_dir: Path | None = None,
) -> Path:
    """Build output MP4 path for a trimmed clip."""
    target_dir = resolve_output_dir(video_path, output_dir)
    start_label = _seconds_to_label(start_seconds)
    end_label = _seconds_to_label(end_seconds)
    return target_dir / f"{video_path.stem}_{suffix}_{start_label}_{end_label}.mp4"


def _run_ffmpeg(command: list[str]) -> None:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"FFmpeg error: {details[-800:]}")


def export_video_segment(
    video_path: Path,
    start_seconds: float,
    end_seconds: float,
    output_path: Path,
    log: LogCallback,
) -> Path:
    """Export [start, end] segment to a new MP4 file."""
    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")

    if start_seconds < 0 or end_seconds <= start_seconds:
        raise ValueError("Invalid trim range: end must be greater than start.")

    ffmpeg_path = resolve_ffmpeg_path()
    if ffmpeg_path is None:
        raise RuntimeError("FFmpeg not found. Install FFmpeg to export video clips.")

    ensure_ffmpeg_on_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    log(f"Export clip: {_seconds_to_label(start_seconds)} -> {_seconds_to_label(end_seconds)}")
    log(f"Output file: {output_path}")

    copy_command = [
        str(ffmpeg_path),
        "-y",
        "-ss",
        f"{start_seconds:.3f}",
        "-to",
        f"{end_seconds:.3f}",
        "-i",
        str(video_path),
        "-c",
        "copy",
        "-avoid_negative_ts",
        "make_zero",
        str(output_path),
    ]

    try:
        _run_ffmpeg(copy_command)
        if output_path.stat().st_size > 0:
            log("Clip saved (stream copy).")
            return output_path
    except RuntimeError:
        log("Stream copy failed, re-encoding...")

    if output_path.exists():
        output_path.unlink(missing_ok=True)

    encode_command = [
        str(ffmpeg_path),
        "-y",
        "-ss",
        f"{start_seconds:.3f}",
        "-to",
        f"{end_seconds:.3f}",
        "-i",
        str(video_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    _run_ffmpeg(encode_command)
    log("Clip saved (re-encoded).")
    return output_path


def export_remove_start(
    video_path: Path,
    cut_before_seconds: float,
    duration_seconds: float,
    output_dir: Path | None,
    log: LogCallback,
) -> Path:
    """Remove the beginning: keep video from cut point to the end."""
    end_seconds = duration_seconds if duration_seconds > 0 else cut_before_seconds + 1
    output_path = build_trim_output_path(
        video_path,
        cut_before_seconds,
        end_seconds,
        "trimmed_start",
        output_dir,
    )
    return export_video_segment(video_path, cut_before_seconds, end_seconds, output_path, log)


def export_remove_end(
    video_path: Path,
    cut_after_seconds: float,
    output_dir: Path | None,
    log: LogCallback,
) -> Path:
    """Remove the ending: keep video from the start to cut point."""
    output_path = build_trim_output_path(
        video_path,
        0.0,
        cut_after_seconds,
        "trimmed_end",
        output_dir,
    )
    return export_video_segment(video_path, 0.0, cut_after_seconds, output_path, log)


def export_clip(
    video_path: Path,
    start_seconds: float,
    end_seconds: float,
    output_dir: Path | None,
    log: LogCallback,
) -> Path:
    """Save only the selected fragment."""
    output_path = build_trim_output_path(
        video_path,
        start_seconds,
        end_seconds,
        "clip",
        output_dir,
    )
    return export_video_segment(video_path, start_seconds, end_seconds, output_path, log)
