"""Core transcription logic (FFmpeg check, Whisper, GPU, file output)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from config import (
    OBSIDIAN_VAULT_PATH,
    OUTPUT_FILE_EXTENSION,
    PARAGRAPH_MAX_SECONDS,
    PARAGRAPH_TARGET_SECONDS,
)

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[float], None]

# NVIDIA CUDA PyTorch (Windows, CUDA 12.4):
#   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
# NVIDIA CUDA PyTorch (Windows, CUDA 12.1):
#   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
# CPU-only fallback:
#   pip install torch torchvision torchaudio


def resolve_device() -> str:
    """Return 'cuda' when an NVIDIA GPU is available, otherwise 'cpu'."""
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "PyTorch is not installed. Install it with CUDA support (see transcription_service.py)."
        ) from exc

    return "cuda" if torch.cuda.is_available() else "cpu"


def describe_device(device: str) -> str:
    """Human-readable device label for logs."""
    if device != "cuda":
        return "cpu"

    try:
        import torch

        name = torch.cuda.get_device_name(0)
        return f"cuda ({name})"
    except Exception:
        return "cuda"


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


def group_segments_into_paragraphs(
    segments: list[dict],
    target_seconds: int = PARAGRAPH_TARGET_SECONDS,
    max_seconds: int = PARAGRAPH_MAX_SECONDS,
) -> list[tuple[float, str]]:
    """
    Merge Whisper segments into readable paragraphs (~30–60 s each).

    A new paragraph starts when the block reaches target length, exceeds max length,
    or the speaker pauses for more than 2 seconds.
    """
    paragraphs: list[tuple[float, str]] = []
    block_start: float | None = None
    block_end: float = 0.0
    block_texts: list[str] = []

    def flush() -> None:
        nonlocal block_start, block_end, block_texts
        if block_start is None or not block_texts:
            block_start = None
            block_texts = []
            return
        paragraphs.append((block_start, " ".join(block_texts)))
        block_start = None
        block_texts = []

    for segment in segments:
        text = segment.get("text", "").strip()
        if not text:
            continue

        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))

        if block_start is None:
            block_start = start
            block_texts = [text]
            block_end = end
            continue

        pause_seconds = start - block_end
        block_duration = block_end - block_start

        if pause_seconds > 2.0 or block_duration >= target_seconds:
            flush()
            block_start = start
            block_texts = [text]
            block_end = end
            continue

        block_texts.append(text)
        block_end = end

        if block_end - block_start >= max_seconds:
            flush()

    flush()
    return paragraphs


def format_segments_grouped(
    segments: list[dict],
    target_seconds: int = PARAGRAPH_TARGET_SECONDS,
    max_seconds: int = PARAGRAPH_MAX_SECONDS,
) -> str:
    """Build LLM-friendly text: one timestamp per logical paragraph."""
    paragraphs = group_segments_into_paragraphs(segments, target_seconds, max_seconds)
    if not paragraphs:
        return ""

    lines = [
        f"{format_timestamp(start)} {text}"
        for start, text in paragraphs
    ]
    return "\n\n".join(lines)


def build_metadata_header(video_name: str, processed_at: datetime | None = None) -> str:
    """YAML-style header for Obsidian / AnythingLLM."""
    when = processed_at or datetime.now()
    date_label = when.strftime("%Y-%m-%d %H:%M")
    return (
        "---\n"
        f"Название: {video_name}\n"
        f"Дата обработки: {date_label}\n"
        "Источник: Локальное видео\n"
        "---\n\n"
    )


def resolve_output_dir(video_path: Path, output_dir: Path | None) -> Path:
    """
    Return folder for output files.

    Priority: GUI output folder → Obsidian vault path → video directory.
    """
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    if OBSIDIAN_VAULT_PATH is not None:
        obsidian_dir = Path(OBSIDIAN_VAULT_PATH)
        obsidian_dir.mkdir(parents=True, exist_ok=True)
        return obsidian_dir

    return video_path.parent


def build_output_path(video_path: Path, output_dir: Path | None = None) -> Path:
    """Return transcription path: {name}_transcription.txt or .md."""
    target_dir = resolve_output_dir(video_path, output_dir)
    extension = OUTPUT_FILE_EXTENSION if OUTPUT_FILE_EXTENSION in {".txt", ".md"} else ".md"
    return target_dir / f"{video_path.stem}_transcription{extension}"


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


def _load_whisper_model(model_name: str, device: str, log: LogCallback):
    """Load Whisper model and move it to the selected device."""
    import whisper

    try:
        model = whisper.load_model(model_name)
        model.to(device)
        return model
    except Exception as exc:
        error_text = str(exc).lower()
        if device == "cuda" and ("out of memory" in error_text or "cuda" in error_text):
            log("Не удалось загрузить модель на GPU — переключение на CPU...")
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            model = whisper.load_model(model_name)
            model.to("cpu")
            return model
        raise RuntimeError(
            f"Failed to load model '{model_name}'. "
            f"Try a smaller model if you run out of memory. Details: {exc}"
        ) from exc


def _transcribe_audio(model, audio_source: Path, device: str, log: LogCallback) -> dict:
    """Run Whisper transcribe with fp16 on CUDA and safe CPU fallback."""
    import torch

    use_fp16 = device == "cuda"
    audio_path = str(audio_source)

    try:
        return model.transcribe(audio_path, verbose=False, fp16=use_fp16)
    except RuntimeError as exc:
        error_text = str(exc).lower()
        if device == "cuda" and "out of memory" in error_text:
            log("Нехватка VRAM на GPU — повтор на CPU (fp16=False)...")
            model.to("cpu")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            return model.transcribe(audio_path, verbose=False, fp16=False)
        raise
    except MemoryError:
        raise
    except Exception as exc:
        error_text = str(exc).lower()
        if "cuda" in error_text and "out of memory" in error_text:
            log("Нехватка VRAM на GPU — повтор на CPU (fp16=False)...")
            model.to("cpu")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            return model.transcribe(audio_path, verbose=False, fp16=False)
        raise


def transcribe_video(
    video_path: Path,
    model_name: str,
    log: LogCallback,
    set_progress: ProgressCallback,
    output_dir: Path | None = None,
) -> str:
    """
    Load Whisper model and transcribe the given video file.

    Uses CUDA + fp16 when available; falls back to CPU on VRAM errors.
    """
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

    device = resolve_device()
    device_label = describe_device(device)
    startup_message = f"Транскрибация запущена на устройстве: {device_label}"
    print(startup_message)
    log(startup_message)

    set_progress(0.15)
    log(f"Loading Whisper model '{model_name}' on {device_label}...")
    model = _load_whisper_model(model_name, device, log)
    active_device = next(model.parameters()).device.type
    use_fp16 = active_device == "cuda"
    if use_fp16:
        log("FP16 включён (CUDA).")
    else:
        log("FP16 выключен (CPU).")

    set_progress(0.25)
    audio_source = get_whisper_audio_source(video_path, log)

    set_progress(0.35)
    log("Transcription started. This may take a while...")

    try:
        result = _transcribe_audio(model, audio_source, active_device, log)
    except MemoryError as exc:
        raise MemoryError(
            f"Not enough memory for model '{model_name}'. "
            "Try a smaller model (tiny or base)."
        ) from exc
    except Exception as exc:
        error_text = str(exc).lower()
        if "invalid data" in error_text or "moov atom not found" in error_text:
            raise ValueError(
                "The video file is corrupted or was not fully downloaded."
            ) from exc
        raise RuntimeError(f"Transcription error: {exc}") from exc

    set_progress(0.85)
    segments = result.get("segments", [])
    body_text = format_segments_grouped(segments)

    if not body_text.strip():
        body_text = result.get("text", "").strip()
        if not body_text:
            raise RuntimeError("Transcription returned empty text.")

    processed_at = datetime.now()
    file_content = build_metadata_header(video_path.stem, processed_at) + body_text

    output_path = build_output_path(video_path, output_dir)
    log(f"Saving result: {output_path}")
    save_transcription(output_path, file_content)

    set_progress(1.0)
    log("Transcription completed successfully.")
    return body_text
