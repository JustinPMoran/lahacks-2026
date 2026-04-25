import argparse
import os
import shutil
import sys
import time
from functools import partial
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs import stream
from elevenlabs.client import ElevenLabs

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

client: ElevenLabs | None = None

VOICE_ID = "JBFqnCBsd6RMkjVDRZzb" # Replace with your hospital-appropriate voice
MODEL_ID = "eleven_turbo_v2_5"
DEFAULT_MESSAGE = "Emergency Alert: Ambulance 4 arriving. Preparing ER for trauma intake."


def ensure_runtime_dependencies():
    if shutil.which("mpv") is None:
        print("Error: 'mpv' is not installed or not in your PATH.")
        print("Install it via 'brew install mpv' (Mac) or 'apt install mpv' (Linux).")
        sys.exit(1)


def get_client() -> ElevenLabs:
    global client

    if client is None:
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not set. Add it to ai-voice-agent/.env.")
        client = ElevenLabs(api_key=api_key)

    return client

def motion_detected():
    """Predicate placeholder for future motion trigger integration."""
    return False

def speak_to_hospital(info_text, *, voice_id=VOICE_ID, model_id=MODEL_ID):
    print(f"--- Sending Voice Update: {info_text} ---")
    try:
        audio_stream = get_client().text_to_speech.stream(
            text=info_text,
            voice_id=voice_id,
            model_id=model_id,
            optimize_streaming_latency=4
        )
        stream(audio_stream)
    except Exception as e:
        print(f"Error connecting to ElevenLabs: {e}")

def run_agent(
    trigger="manual",
    message=DEFAULT_MESSAGE,
    motion_detector=motion_detected,
    speaker=speak_to_hospital,
    sleep_fn=time.sleep,
    *,
    require_mpv=True,
    cooldown_seconds=10,
    poll_interval=0.1,
    max_cycles=None,
):
    if require_mpv:
        ensure_runtime_dependencies()

    print("AI Voice Agent is standby. Monitoring predicate...")

    if trigger == "manual":
        speaker(message)
        return

    if trigger != "motion":
        raise ValueError("trigger must be either 'manual' or 'motion'")

    cycles = 0
    
    try:
        while True:
            if motion_detector():
                speaker(message)
                sleep_fn(cooldown_seconds)

            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                break

            sleep_fn(poll_interval)
            
    except KeyboardInterrupt:
        print("\nAgent shut down.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run the ElevenLabs hospital voice agent.")
    parser.add_argument(
        "--trigger",
        choices=("manual", "motion"),
        default="manual",
        help="manual speaks once immediately; motion polls the predicate until it turns true",
    )
    parser.add_argument(
        "--message",
        default=DEFAULT_MESSAGE,
        help="The hospital update to speak",
    )
    parser.add_argument(
        "--voice-id",
        default=VOICE_ID,
        help="ElevenLabs voice ID to use",
    )
    parser.add_argument(
        "--model-id",
        default=MODEL_ID,
        help="ElevenLabs model ID to use",
    )
    parser.add_argument(
        "--cooldown-seconds",
        type=float,
        default=10.0,
        help="Pause after speaking when in motion mode",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.1,
        help="How often to re-check the motion predicate",
    )
    parser.add_argument(
        "--no-mpv-check",
        action="store_true",
        help="Skip the mpv availability check for local testing",
    )
    return parser.parse_args(argv)

if __name__ == "__main__":
    args = parse_args()
    speaker = partial(speak_to_hospital, voice_id=args.voice_id, model_id=args.model_id)
    run_agent(
        trigger=args.trigger,
        message=args.message,
        speaker=speaker,
        require_mpv=not args.no_mpv_check,
        cooldown_seconds=args.cooldown_seconds,
        poll_interval=args.poll_interval,
    )