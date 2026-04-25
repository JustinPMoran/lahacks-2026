import argparse
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs import stream
from elevenlabs.client import ElevenLabs
from elevenlabs.types import (
    AgentConfig,
    ConversationHistoryTranscriptCommonModelInput,
    ConversationSimulationSpecification,
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_MODEL_ID = "eleven_turbo_v2_5"


def ensure_mpv_installed() -> None:
    if shutil.which("mpv") is None:
        print(
            "Error: mpv is required for playback but was not found in PATH. "
            "Install mpv and try again.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send one text message to an ElevenLabs nurse agent and speak the response."
    )
    parser.add_argument(
        "--message",
        default=None,
        help="Message to send to the nurse agent. If omitted, you'll be prompted in the terminal.",
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
        "--api-key-env",
        default="ELEVENLABS_API_KEY",
        help="Environment variable name that stores your ElevenLabs API key.",
    )
    parser.add_argument(
        "--voice-id",
        default=DEFAULT_VOICE_ID,
        help="ElevenLabs voice ID used for speaking the nurse response.",
    )
    parser.add_argument(
        "--model-id",
        default=DEFAULT_MODEL_ID,
        help="ElevenLabs TTS model ID used for speaking the nurse response.",
    )
    parser.add_argument(
        "--no-playback",
        action="store_true",
        help="Skip voice playback and only print the nurse response text.",
    )

    return parser.parse_args()


def get_nurse_reply(client: ElevenLabs, agent_id: str, message: str) -> str:
    simulation_spec = ConversationSimulationSpecification(
        simulated_user_config=AgentConfig(first_message=""),
        partial_conversation_history=[
            ConversationHistoryTranscriptCommonModelInput(
                role="user",
                message=message,
                time_in_call_secs=0,
            )
        ],
    )

    result = client.conversational_ai.agents.simulate_conversation(
        agent_id=agent_id,
        simulation_specification=simulation_spec,
        new_turns_limit=1,
    )

    for turn in reversed(result.simulated_conversation):
        if turn.role == "agent" and turn.message:
            return turn.message

    raise RuntimeError("Agent did not return a text response for this message.")


def speak_text(client: ElevenLabs, text: str, voice_id: str, model_id: str) -> None:
    audio_stream = client.text_to_speech.stream(
        voice_id=voice_id,
        text=text,
        model_id=model_id,
        optimize_streaming_latency=4,
    )
    stream(audio_stream)


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
    if not api_key:
        print(
            f"Error: {args.api_key_env} is not set. Add it to {BASE_DIR / '.env'} or your shell environment.",
            file=sys.stderr,
        )
        return 1

    message = args.message or input("Enter message for Nurse Agent: ").strip()
    if not message:
        print("Error: message cannot be empty.", file=sys.stderr)
        return 1

    if not args.no_playback:
        ensure_mpv_installed()

    client = ElevenLabs(api_key=api_key)
    try:
        reply = get_nurse_reply(client=client, agent_id=agent_id, message=message)
    except Exception as exc:
        print(f"Error while querying Nurse Agent: {exc}", file=sys.stderr)
        return 1

    print(f"[You] {message}")
    print(f"[Nurse Agent] {reply}")

    if not args.no_playback:
        try:
            speak_text(client=client, text=reply, voice_id=args.voice_id, model_id=args.model_id)
        except Exception as exc:
            print(f"Error while generating or playing voice: {exc}", file=sys.stderr)
            return 1

    return 0

if __name__ == "__main__":
    raise SystemExit(main())