import argparse
import os
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start an ElevenLabs real-time Conversational AI session over default mic and speakers."
    )
    parser.add_argument(
        "--agent-id",
        default=None,
        help="ElevenLabs Conversational AI agent ID. If omitted, it is read from the env var set by --agent-id-env.",
    )
    parser.add_argument(
        "--agent-id-env",
        default="ELEVENLABS_AGENT_ID",
        help="Environment variable name that stores your ElevenLabs Conversational AI agent ID.",
    )
    parser.add_argument(
        "--user-id",
        default=None,
        help="Optional user ID for conversation metadata.",
    )
    parser.add_argument(
        "--api-key-env",
        default="ELEVENLABS_API_KEY",
        help="Environment variable name that stores your ElevenLabs API key.",
    )
    parser.add_argument(
        "--context",
        default=None,
        help="Optional contextual update sent after session start (for triage details, etc.).",
    )

    parser.set_defaults(requires_auth=True)
    parser.add_argument(
        "--requires-auth",
        dest="requires_auth",
        action="store_true",
        help="Use authenticated websocket session (default).",
    )
    parser.add_argument(
        "--no-requires-auth",
        dest="requires_auth",
        action="store_false",
        help="Use unauthenticated session for publicly accessible agents.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    agent_id = args.agent_id or os.getenv(args.agent_id_env) or os.getenv("AGENT_ID")
    if not agent_id:
        print(
            f"Error: no agent ID provided. Use --agent-id, or set {args.agent_id_env} in {BASE_DIR / '.env'}.",
            file=sys.stderr,
        )
        return 1

    api_key = os.getenv(args.api_key_env)
    if args.requires_auth and not api_key:
        print(
            f"Error: {args.api_key_env} is not set. Add it to {BASE_DIR / '.env'} or your shell environment.",
            file=sys.stderr,
        )
        return 1

    try:
        audio_interface = DefaultAudioInterface()
    except ImportError:
        print(
            "Error: DefaultAudioInterface requires pyaudio. Install it, then retry.\n"
            "Windows tip: pip install pipwin ; pipwin install pyaudio",
            file=sys.stderr,
        )
        return 1

    client = ElevenLabs(api_key=api_key)
    session_ended = threading.Event()

    def on_user_transcript(text: str) -> None:
        print(f"[You] {text}")

    def on_agent_response(text: str) -> None:
        print(f"[Nurse Agent] {text}")

    def on_agent_response_correction(original: str, corrected: str) -> None:
        print(f"[Nurse Agent correction] {original} -> {corrected}")

    def on_end_session() -> None:
        print("Session ended by server.")
        session_ended.set()

    conversation = Conversation(
        client,
        agent_id=agent_id,
        user_id=args.user_id,
        requires_auth=args.requires_auth,
        audio_interface=audio_interface,
        callback_user_transcript=on_user_transcript,
        callback_agent_response=on_agent_response,
        callback_agent_response_correction=on_agent_response_correction,
        callback_end_session=on_end_session,
    )

    conversation.start_session()
    print("Conversation started. Speak into your default microphone.")
    print("Press Ctrl+C to end the session.")

    if args.context:
        conversation.send_contextual_update(args.context)

    try:
        while not session_ended.is_set():
            session_ended.wait(timeout=0.25)
    except KeyboardInterrupt:
        print("Stopping session...")
        conversation.end_session()

    conversation_id = conversation.wait_for_session_end()
    if conversation_id:
        print(f"Conversation ID: {conversation_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
