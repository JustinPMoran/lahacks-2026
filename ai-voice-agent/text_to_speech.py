import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_MODEL_ID = "eleven_turbo_v2_5"
DEFAULT_OUTPUT_FILE = BASE_DIR / "tts_output.mp3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert text to speech with ElevenLabs and save/play the result."
    )
    parser.add_argument(
        "--text",
        default=None,
        help="Text to convert to speech. If omitted, you'll be prompted in the terminal.",
    )
    parser.add_argument(
        "--api-key-env",
        default="ELEVENLABS_API_KEY",
        help="Environment variable name that stores your ElevenLabs API key.",
    )
    parser.add_argument(
        "--voice-id",
        default=os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID),
        help="ElevenLabs voice ID used for TTS. You can pass your new voice ID here.",
    )
    parser.add_argument(
        "--model-id",
        default=DEFAULT_MODEL_ID,
        help="ElevenLabs TTS model ID.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_FILE),
        help="Output MP3 file path.",
    )
    parser.add_argument(
        "--no-playback",
        action="store_true",
        help="Skip local playback after generating audio.",
    )

    return parser.parse_args()


def ensure_mpv_installed() -> None:
    if shutil.which("mpv") is None:
        print(
            "Error: mpv is required for playback but was not found in PATH. "
            "Install mpv or use --no-playback.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def synthesize_to_file(
    client: ElevenLabs,
    text: str,
    voice_id: str,
    model_id: str,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    audio_stream = client.text_to_speech.convert(
        voice_id=voice_id,
        model_id=model_id,
        text=text,
        output_format="mp3_44100_128",
    )

    with output_path.open("wb") as audio_file:
        for chunk in audio_stream:
            if chunk:
                audio_file.write(chunk)

    return output_path


def play_with_mpv(audio_file: Path) -> None:
    subprocess.run(["mpv", "--no-video", str(audio_file)], check=True)


def main() -> int:
    args = parse_args()

    api_key = os.getenv(args.api_key_env)
    if not api_key:
        print(
            f"Error: {args.api_key_env} is not set. Add it to {BASE_DIR / '.env'} or your shell environment.",
            file=sys.stderr,
        )
        return 1

    text = args.text or input("Enter text to convert: ").strip()
    if not text:
        print("Error: text cannot be empty.", file=sys.stderr)
        return 1

    output_path = Path(args.output).expanduser().resolve()

    client = ElevenLabs(api_key=api_key)
    try:
        generated_file = synthesize_to_file(
            client=client,
            text=text,
            voice_id=args.voice_id,
            model_id=args.model_id,
            output_path=output_path,
        )
    except Exception as exc:
        print(f"Error while generating speech: {exc}", file=sys.stderr)
        return 1

    print(f"Generated audio: {generated_file}")
    print(f"Voice ID: {args.voice_id}")
    print(f"Model ID: {args.model_id}")

    if not args.no_playback:
        try:
            ensure_mpv_installed()
            play_with_mpv(generated_file)
        except Exception as exc:
            print(f"Error while playing audio: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
