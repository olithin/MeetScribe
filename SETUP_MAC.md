# MeetScribe — macOS setup

Quick guide for teammates (GitHub clone, ZIP, or copy from Windows).

## One-time prerequisites

1. **Homebrew** (if missing): [brew.sh](https://brew.sh)

2. **Python 3.10+**, **FFmpeg**, and **VLC** (audio player and **L** pop-out window):

   ```bash
   brew install python ffmpeg vlc
   ```

   Or install Python from [python.org](https://www.python.org/downloads/) and still use Homebrew for FFmpeg/VLC:

   ```bash
   brew install ffmpeg vlc
   ```

3. Verify:

   ```bash
   python3 --version
   ffmpeg -version
   ```

## Install the app

```bash
git clone https://github.com/olithin/MeetScribe.git
cd MeetScribe
```

Or unpack a ZIP and `cd` into the project folder.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

chmod +x run.sh
./run.sh
```

> Do **not** copy a `.venv` folder from Windows — create a fresh one on Mac.

## Run again later

```bash
cd /path/to/MeetScribe
./run.sh
```

`run.sh` uses `.venv/bin/python` automatically when present.

### External venv (optional)

```bash
python3 -m venv ~/.venvs/meet-scribe
source ~/.venvs/meet-scribe/bin/activate
pip install -r requirements.txt
```

Add to `~/.zshrc`:

```bash
export MEETSCRIBE_VENV="$HOME/.venvs/meet-scribe"
```

## First launch

- Whisper downloads the model from the internet (~150 MB–1.5 GB for `small`).
- Logs should show: `FFmpeg detected` and `VLC detected`.

## If macOS blocks the script

**System Settings → Privacy & Security** → Open Anyway.

Or in Terminal:

```bash
xattr -d com.apple.quarantine run.sh 2>/dev/null
chmod +x run.sh
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `FFmpeg not found` | `brew install ffmpeg`, restart Terminal |
| `VLC not found` | `brew install vlc`, restart the app |
| `No module named ...` | `source .venv/bin/activate` and `pip install -r requirements.txt` |
| Slow transcription | Normal on CPU-only Mac; try `tiny` or `base` model |

See also [README.md](README.md).
