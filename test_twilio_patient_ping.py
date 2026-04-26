#!/usr/bin/env python
# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.
from __future__ import annotations

import argparse
import html
import os
import sys
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


ROOT_DIR = Path(__file__).resolve().parent


def load_env() -> None:
    if load_dotenv is None:
        return
    load_dotenv(ROOT_DIR / ".env")
    # Fallback for setups that keep secrets under ai-voice-agent/.
    load_dotenv(ROOT_DIR / "ai-voice-agent" / ".env", override=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Place a Twilio test phone call for RuView patient-tag alerts."
    )
    parser.add_argument(
        "--to",
        default=None,
        help="Destination phone number in E.164 format. Defaults to TWILIO_PATIENT_ALERT_TO.",
    )
    parser.add_argument(
        "--floor",
        default="LEVEL 1",
        help="Floor label included in the spoken alert message.",
    )
    parser.add_argument(
        "--patient-count",
        type=int,
        default=1,
        help="Patient count included in the spoken alert message.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="HTTP timeout in seconds. Defaults to TWILIO_CALL_TIMEOUT_SECONDS or 10.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload details without placing a call.",
    )
    parser.add_argument(
        "--audio-url",
        default=None,
        help="Public HTTPS URL for an MP3/WAV Twilio should play. Defaults to TWILIO_PATIENT_ALERT_AUDIO_URL.",
    )
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"Missing required env var: {name}", file=sys.stderr)
        raise SystemExit(1)
    return value


def main() -> int:
    load_env()
    args = parse_args()

    account_sid = require_env("TWILIO_ACCOUNT_SID")
    api_key_sid = require_env("TWILIO_API_KEY_SID")
    api_key_secret = require_env("TWILIO_API_KEY_SECRET")
    from_number = require_env("TWILIO_FROM_NUMBER")
    to_number = (args.to or os.environ.get("TWILIO_PATIENT_ALERT_TO", "+17605768000")).strip()
    audio_url = (args.audio_url or os.environ.get("TWILIO_PATIENT_ALERT_AUDIO_URL", "")).strip()
    timeout = args.timeout or float(os.environ.get("TWILIO_CALL_TIMEOUT_SECONDS", "10"))

    call_text = (
        f"RuView test alert. Patients tag changed on {args.floor}. "
        f"Total tagged patients: {max(0, args.patient_count)}."
    )
    if audio_url:
        twiml = f"<Response><Play>{html.escape(audio_url)}</Play></Response>"
    else:
        twiml = f"<Response><Say voice='alice'>{html.escape(call_text)}</Say></Response>"
    payload = {"To": to_number, "From": from_number, "Twiml": twiml}
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"

    print(f"Prepared test call to {to_number} from {from_number}")
    if audio_url:
        print(f"Audio URL: {audio_url}")
    else:
        print(f"Message: {call_text}")
    if args.dry_run:
        print("Dry run enabled; skipping Twilio API call.")
        return 0

    try:
        response = requests.post(
            url,
            data=payload,
            auth=(api_key_sid, api_key_secret),
            timeout=max(1.0, timeout),
        )
    except requests.RequestException as exc:
        print(f"Twilio request failed: {exc}", file=sys.stderr)
        return 1

    if response.status_code >= 300:
        print(f"Twilio rejected call. status={response.status_code}", file=sys.stderr)
        print(response.text[:400], file=sys.stderr)
        return 1

    call_sid = "unknown"
    try:
        call_sid = response.json().get("sid", "unknown")
    except ValueError:
        pass
    print(f"Success: call queued. sid={call_sid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
