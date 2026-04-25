# ai-voice-agent

Minimal ElevenLabs voice agent for the hackathon demo. It can either speak once from a terminal command or poll a motion predicate placeholder.

## What you need

- An ElevenLabs account
- An ElevenLabs API key
- `mpv` installed locally for audio playback

No other account is required unless you later wire in a real motion sensor or camera pipeline.

## Setup

Run the single setup script from inside the `ai-voice-agent` folder.

### Windows

```powershell
cd ai-voice-agent
.\setup.ps1
```

This script will:

- install both repository and voice-agent Python packages into the shared `../.venv`
- best-effort install `mpv` with `winget` when available

### macOS / Linux

```bash
cd ai-voice-agent
python3 -m venv ../.venv
source ../.venv/bin/activate
pip install -r ../requirements.txt -r requirements.txt
```

## Run

Speak once from the terminal:

```powershell
python main.py --trigger manual --message "Ambulance 4 arriving. Preparing ER for trauma intake."
```

Poll the motion predicate placeholder:

```powershell
python main.py --trigger motion
```

## Notes

- `motion_detected()` is intentionally just a predicate placeholder right now.
- `main.py` is the only runtime path you need for the ElevenLabs track.
