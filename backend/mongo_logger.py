# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.
"""
Stream ESP32 WiFi sensing telemetry to MongoDB Atlas.

The csi_recv firmware emits MOTION and CSI_DATA lines over UART. This logger
keeps the original demo collections (`motion_log` and optional `csi_raw`) while
also creating training-data documents:

    devices              one document per ESP32 board
    capture_sessions     one document per logger run
    sensor_samples       one document per CSI sample window

If GOOGLE_API_KEY is configured, each sensor sample is enriched with a compact
Gemini JSON response. Deterministic code still owns identifiers, timestamps,
shape, dtype, and raw payload fields so training data stays stable.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient

from csi import open_serial, parse_amplitudes

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # Gemini enrichment is optional.
    genai = None
    genai_types = None


LEVEL_LABEL = {0: "QUIET", 1: "MOTION", 2: "BUSY"}
DEFAULT_DEVICE_ID = "esp32s3_001"
DEFAULT_SAMPLE_WINDOW_MS = 5000


def load_environment() -> None:
    """Load .env from the repo root, falling back to the current directory."""
    repo_root = Path(__file__).resolve().parent.parent
    for candidate in (repo_root / ".env", Path.cwd() / ".env"):
        if candidate.exists():
            load_dotenv(candidate)
            break


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def csv_env(name: str, default: list[str]) -> list[str]:
    value = os.environ.get(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def csv_arg(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def make_session_id(start_time: datetime) -> str:
    return f"session_{start_time:%Y_%m_%d_%H%M%S}"


def number_stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"min": None, "max": None, "mean": None, "count": 0}
    return {
        "min": round(float(min(values)), 4),
        "max": round(float(max(values)), 4),
        "mean": round(float(sum(values) / len(values)), 4),
        "count": len(values),
    }


def estimate_snr_db(signal_mean: float, noise_std: float) -> float | None:
    if signal_mean <= 0 or noise_std <= 0:
        return None
    return round(20.0 * math.log10(signal_mean / noise_std), 2)


def estimate_packet_loss(seqs: list[int]) -> float:
    unique = sorted(set(seqs))
    if len(unique) < 2:
        return 0.0
    expected = unique[-1] - unique[0] + 1
    if expected <= 0:
        return 0.0
    return round(max(0.0, (expected - len(unique)) / expected), 4)


def parse_csi_metadata(text: str) -> dict[str, Any] | None:
    head = text.split(',"', 1)[0].split(",")
    try:
        seq = int(head[1])
        mac = head[2]
        rssi = int(head[3])
    except (IndexError, ValueError):
        return None
    return {
        "seq": seq,
        "mac": mac,
        "sender_id": int(mac.split(":")[-1], 16) if ":" in mac else None,
        "rssi": rssi,
    }


def default_pin_map() -> dict[str, Any]:
    return {
        "adc_channels": [
            {"gpio": 1, "adc_unit": "ADC1", "adc_channel": 0, "label": "mic_in"},
            {"gpio": 2, "adc_unit": "ADC1", "adc_channel": 1, "label": "fsr_1"},
        ],
        "digital_inputs": [
            {"gpio": 4, "label": "pir_motion"},
            {"gpio": 5, "label": "reed_switch"},
        ],
        "i2c": {
            "sda_gpio": 8,
            "scl_gpio": 9,
            "attached_sensors": [
                {"name": "imu", "model": "BMI160", "address": "0x68"},
            ],
        },
    }


def make_device_doc(args: argparse.Namespace, created_at: datetime) -> dict[str, Any]:
    return {
        "_id": args.device_id,
        "device_type": args.device_type,
        "firmware": {
            "name": args.firmware_name,
            "version": args.firmware_version,
            "esp_idf_version": args.esp_idf_version,
        },
        "hardware": {
            "chip": args.hardware_chip,
            "board_model": args.board_model,
            "mac_addr_wifi_sta": args.mac_addr_wifi_sta,
            "mac_addr_wifi_ap": args.mac_addr_wifi_ap,
        },
        "capabilities": {
            "wifi": True,
            "wifi_csi": True,
            "adc": True,
            "gpio": True,
            "internal_temperature": True,
            "i2c": True,
            "spi": True,
            "uart": True,
        },
        "pin_map": default_pin_map(),
        "created_at": created_at,
        "updated_at": created_at,
    }


def make_capture_session_doc(
    args: argparse.Namespace,
    session_id: str,
    start_time: datetime,
) -> dict[str, Any]:
    return {
        "_id": session_id,
        "device_id": args.device_id,
        "subject_id": args.subject_id,
        "activity": {
            "name": args.activity_name,
            "label_id": args.activity_label_id,
            "annotation_source": args.annotation_source,
        },
        "environment": {
            "site": args.env_site,
            "room": args.env_room,
            "notes": args.env_notes,
        },
        "capture_config": {
            "sensor_mode": "wifi_csi",
            "wifi": {
                "mode": args.wifi_mode,
                "channel": args.wifi_channel,
                "bandwidth": args.wifi_bandwidth,
                "router_bssid": args.router_bssid,
            },
            "sampling": {
                "sample_rate_hz": args.sample_rate_hz,
                "window_ms": args.sample_window_ms,
            },
            "normalization": {
                "applied_on_device": False,
            },
        },
        "start_time": start_time,
        "end_time": None,
        "tags": args.session_tags,
    }


def summarize_motion_events(
    events: list[dict[str, Any]],
    start_time: datetime,
    end_time: datetime,
) -> dict[str, Any]:
    in_window = [event for event in events if start_time <= event["ts"] <= end_time]
    if not in_window:
        return {"event_count": 0, "max_score": None, "level_counts": {}}
    levels = Counter(LEVEL_LABEL.get(event["level"], "UNKNOWN") for event in in_window)
    return {
        "event_count": len(in_window),
        "max_score": round(max(float(event["score"]) for event in in_window), 4),
        "level_counts": dict(levels),
    }


class CsiWindowBuilder:
    def __init__(
        self,
        *,
        session_id: str,
        device_id: str,
        subject_id: str,
        activity_name: str,
        activity_label_id: int,
        window_ms: int,
    ) -> None:
        self.session_id = session_id
        self.device_id = device_id
        self.subject_id = subject_id
        self.activity_name = activity_name
        self.activity_label_id = activity_label_id
        self.window_ms = window_ms
        self.sample_index = 0
        self._entries: list[dict[str, Any]] = []

    def add(
        self,
        ts: datetime,
        amp: Any,
        metadata: dict[str, Any],
        recent_motion_events: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        self._entries.append({"ts": ts, "amp": amp, **metadata})
        window_start = self._entries[0]["ts"]
        elapsed_ms = (ts - window_start).total_seconds() * 1000.0
        if elapsed_ms < self.window_ms:
            return None
        return self.flush(recent_motion_events)

    def flush(self, recent_motion_events: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not self._entries:
            return None

        entries = self._entries
        self._entries = []
        self.sample_index += 1

        timestamp_start = entries[0]["ts"]
        timestamp_end = entries[-1]["ts"]
        n_subcarriers = min(int(entry["amp"].size) for entry in entries)
        amplitudes = [entry["amp"][:n_subcarriers] for entry in entries]
        amp_means = [float(amp.mean()) for amp in amplitudes]
        amp_stds = [float(amp.std()) for amp in amplitudes]
        rssi_values = [float(entry["rssi"]) for entry in entries]
        seqs = [int(entry["seq"]) for entry in entries]
        signal_mean = float(sum(amp_means) / len(amp_means)) if amp_means else 0.0
        noise_std = float(sum(amp_stds) / len(amp_stds)) if amp_stds else 0.0
        snr_db = estimate_snr_db(signal_mean, noise_std)
        created_at = utc_now()

        return {
            "_id": f"sample_{self.session_id}_{self.sample_index:08d}",
            "session_id": self.session_id,
            "device_id": self.device_id,
            "subject_id": self.subject_id,
            "activity": {
                "name": self.activity_name,
                "label_id": self.activity_label_id,
            },
            "sensor_type": "wifi_csi",
            "sample_index": self.sample_index,
            "timestamp_start": timestamp_start,
            "timestamp_end": timestamp_end,
            "shape": [len(amplitudes), n_subcarriers],
            "dtype": "float32",
            "preprocessing": {
                "normalized": False,
                "downsampled": False,
                "reshape_rule": "none",
            },
            "quality": {
                "packet_loss": estimate_packet_loss(seqs),
                "snr_db": snr_db,
                "valid": bool(amplitudes and n_subcarriers > 0),
            },
            "payload": {
                "source": "esp32_uart",
                "packet_count": len(amplitudes),
                "seq": {"first": seqs[0], "last": seqs[-1]},
                "mac_addresses": sorted({entry["mac"] for entry in entries}),
                "sender_ids": sorted(
                    sender_id for sender_id in {entry["sender_id"] for entry in entries}
                    if sender_id is not None
                ),
                "rssi_dbm": number_stats(rssi_values),
                "features": {
                    "amp_mean_by_packet": number_stats(amp_means),
                    "amp_std_by_packet": number_stats(amp_stds),
                    "amp_mean": round(signal_mean, 4),
                    "amp_std": round(noise_std, 4),
                    "approx_snr_db": snr_db,
                    "motion": summarize_motion_events(
                        recent_motion_events,
                        timestamp_start,
                        timestamp_end,
                    ),
                },
                "amplitude": {
                    "unit": "magnitude",
                    "subcarriers": n_subcarriers,
                    "frames": [
                        [round(float(value), 4) for value in amp.tolist()]
                        for amp in amplitudes
                    ],
                },
            },
            "created_at": created_at,
        }


class GeminiEnricher:
    def __init__(self, *, api_key: str | None, model: str, enabled: bool) -> None:
        self.model = model
        self.enabled = enabled and bool(api_key) and genai is not None
        self._warned = False
        self.client = genai.Client(api_key=api_key) if self.enabled else None
        if enabled and not api_key:
            self._warn("GOOGLE_API_KEY not set - writing deterministic samples")
        elif enabled and genai is None:
            self._warn("google-genai not installed - writing deterministic samples")

    def _warn(self, message: str) -> None:
        if not self._warned:
            print(f"gemini: {message}", file=sys.stderr)
            self._warned = True

    def enrich(self, sample_doc: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled or self.client is None:
            return {}

        prompt = {
            "task": (
                "Given this compact WiFi CSI sample summary, return strict JSON "
                "with optional quality corrections and concise training notes. "
                "Do not invent identifiers, timestamps, shape, dtype, or raw data."
            ),
            "allowed_response_schema": {
                "quality": {
                    "packet_loss": "number between 0 and 1, optional",
                    "snr_db": "number or null, optional",
                    "valid": "boolean, optional",
                },
                "payload": {
                    "ai_summary": "short string, optional",
                    "inferred_activity": {
                        "name": "string",
                        "confidence": "number between 0 and 1",
                    },
                    "feature_notes": ["short strings"],
                },
            },
            "sample_summary": compact_sample_summary(sample_doc),
        }
        try:
            config = genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            )
            response = self.client.models.generate_content(
                model=self.model,
                contents=json.dumps(prompt),
                config=config,
            )
            text = (getattr(response, "text", "") or "").strip()
            return parse_json_object(text)
        except Exception as exc:  # Keep ingestion alive when Gemini is flaky.
            self._warn(f"enrichment failed ({exc}) - writing deterministic samples")
            return {}


def compact_sample_summary(sample_doc: dict[str, Any]) -> dict[str, Any]:
    payload = sample_doc["payload"]
    return {
        "session_id": sample_doc["session_id"],
        "device_id": sample_doc["device_id"],
        "subject_id": sample_doc["subject_id"],
        "activity": sample_doc["activity"],
        "sensor_type": sample_doc["sensor_type"],
        "sample_index": sample_doc["sample_index"],
        "shape": sample_doc["shape"],
        "quality": sample_doc["quality"],
        "packet_count": payload["packet_count"],
        "rssi_dbm": payload["rssi_dbm"],
        "features": payload["features"],
        "mac_addresses": payload["mac_addresses"],
        "sender_ids": payload["sender_ids"],
    }


def parse_json_object(text: str) -> dict[str, Any]:
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {}


def bounded_float(value: Any, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if minimum <= numeric <= maximum:
        return round(numeric, 4)
    return None


def merge_enrichment(sample_doc: dict[str, Any], enrichment: dict[str, Any]) -> None:
    quality = enrichment.get("quality")
    if isinstance(quality, dict):
        packet_loss = bounded_float(quality.get("packet_loss"), 0.0, 1.0)
        if packet_loss is not None:
            sample_doc["quality"]["packet_loss"] = packet_loss
        if "snr_db" in quality:
            snr_db = quality.get("snr_db")
            if snr_db is None:
                sample_doc["quality"]["snr_db"] = None
            else:
                numeric_snr = bounded_float(snr_db, -100.0, 100.0)
                if numeric_snr is not None:
                    sample_doc["quality"]["snr_db"] = numeric_snr
        if isinstance(quality.get("valid"), bool):
            sample_doc["quality"]["valid"] = quality["valid"]

    payload = enrichment.get("payload")
    if not isinstance(payload, dict):
        return
    if isinstance(payload.get("ai_summary"), str):
        sample_doc["payload"]["ai_summary"] = payload["ai_summary"][:500]
    inferred_activity = payload.get("inferred_activity")
    if isinstance(inferred_activity, dict) and isinstance(inferred_activity.get("name"), str):
        confidence = bounded_float(inferred_activity.get("confidence", 0.0), 0.0, 1.0)
        sample_doc["payload"]["inferred_activity"] = {
            "name": inferred_activity["name"][:100],
            "confidence": confidence if confidence is not None else 0.0,
        }
    feature_notes = payload.get("feature_notes")
    if isinstance(feature_notes, list):
        sample_doc["payload"]["feature_notes"] = [
            note[:200] for note in feature_notes[:8] if isinstance(note, str)
        ]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--port", default=os.environ.get("CSI_SERIAL_PORT", "/dev/cu.usbserial-130"))
    p.add_argument("--baud", type=int, default=env_int("CSI_SERIAL_BAUD", 921600))
    p.add_argument("--node", default=os.environ.get("CSI_NODE_ID", "rx-01"),
                   help="receiver identifier baked into every legacy doc")
    p.add_argument("--flush-seconds", type=float, default=env_float("FLUSH_SECONDS", 1.0),
                   help="how often to bulk-insert buffered docs")
    p.add_argument("--raw", action="store_true", default=env_bool("LOG_RAW_CSI", False),
                   help="also log throttled CSI packets to csi_raw")

    p.add_argument("--device-id", default=os.environ.get("DEVICE_ID", DEFAULT_DEVICE_ID))
    p.add_argument("--device-type", default=os.environ.get("DEVICE_TYPE", "esp32-s3"))
    p.add_argument("--firmware-name", default=os.environ.get("FIRMWARE_NAME", "wifi-sensing-fw"))
    p.add_argument("--firmware-version", default=os.environ.get("FIRMWARE_VERSION", "0.1.0"))
    p.add_argument("--esp-idf-version", default=os.environ.get("ESP_IDF_VERSION", "v5.2.1"))
    p.add_argument("--hardware-chip", default=os.environ.get("HARDWARE_CHIP", "ESP32-S3"))
    p.add_argument("--board-model", default=os.environ.get("BOARD_MODEL", "custom"))
    p.add_argument("--mac-addr-wifi-sta", default=os.environ.get("MAC_ADDR_WIFI_STA", "AA:BB:CC:DD:EE:FF"))
    p.add_argument("--mac-addr-wifi-ap", default=os.environ.get("MAC_ADDR_WIFI_AP", "AA:BB:CC:DD:EE:00"))

    p.add_argument("--session-id", default=os.environ.get("SESSION_ID"))
    p.add_argument("--subject-id", default=os.environ.get("SUBJECT_ID", "participant_01"))
    p.add_argument("--activity-name", default=os.environ.get("ACTIVITY_NAME", "walking"))
    p.add_argument("--activity-label-id", type=int, default=env_int("ACTIVITY_LABEL_ID", 0))
    p.add_argument("--annotation-source", default=os.environ.get("ANNOTATION_SOURCE", "manual"))
    p.add_argument("--env-site", default=os.environ.get("ENV_SITE", "lab_a"))
    p.add_argument("--env-room", default=os.environ.get("ENV_ROOM", "conference_room"))
    p.add_argument("--env-notes", default=os.environ.get("ENV_NOTES", "single person, door closed"))
    p.add_argument(
        "--session-tags",
        type=csv_arg,
        default=csv_env("SESSION_TAGS", ["train", "baseline"]),
    )

    p.add_argument("--wifi-mode", default=os.environ.get("WIFI_MODE", "station"))
    p.add_argument("--wifi-channel", type=int, default=env_int("WIFI_CHANNEL", 6))
    p.add_argument("--wifi-bandwidth", default=os.environ.get("WIFI_BANDWIDTH", "HT20"))
    p.add_argument("--router-bssid", default=os.environ.get("ROUTER_BSSID", "11:22:33:44:55:66"))
    p.add_argument("--sample-rate-hz", type=int, default=env_int("SAMPLE_RATE_HZ", 100))
    p.add_argument("--sample-window-ms", type=int, default=env_int("SAMPLE_WINDOW_MS", DEFAULT_SAMPLE_WINDOW_MS))

    p.add_argument("--gemini-model", default=os.environ.get("GEMINI_MODEL", "gemma-4-26b-a4b-it"))
    p.add_argument("--no-gemini", action="store_true", default=env_bool("DISABLE_GEMINI", False),
                   help="write deterministic samples without Google Gemini enrichment")
    return p


def main() -> int:
    load_environment()
    args = build_parser().parse_args()

    uri = os.environ.get("MONGODB_URI")
    if not uri or "USER:PASSWORD" in uri or "<" in uri:
        print("error: MONGODB_URI not set in .env (copy .env.example to .env and edit)",
              file=sys.stderr)
        return 2

    db_name             = os.environ.get("MONGODB_DB", "csi_demo")
    motion_coll         = os.environ.get("MONGODB_COLLECTION", "motion_log")
    raw_coll_n          = os.environ.get("MONGODB_RAW_COLLECTION", "csi_raw")
    devices_coll_n      = os.environ.get("MONGODB_DEVICES_COLLECTION", "devices")
    sessions_coll_n     = os.environ.get("MONGODB_SESSIONS_COLLECTION", "capture_sessions")
    samples_coll_n      = os.environ.get("MONGODB_SAMPLES_COLLECTION", "sensor_samples")

    client = MongoClient(uri, appname="ruview-demo", serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    print(f"connected to atlas → db={db_name}", file=sys.stderr)

    db = client[db_name]
    devices = db[devices_coll_n]
    sessions = db[sessions_coll_n]
    sensor_samples = db[samples_coll_n]
    motion_log = db[motion_coll]

    devices.create_index([("device_type", ASCENDING)])
    sessions.create_index([("device_id", ASCENDING), ("start_time", ASCENDING)])
    sensor_samples.create_index([("session_id", ASCENDING), ("sample_index", ASCENDING)])
    sensor_samples.create_index([("device_id", ASCENDING), ("timestamp_start", ASCENDING)])
    motion_log.create_index([("ts", ASCENDING)])
    motion_log.create_index([("node", ASCENDING), ("sender_id", ASCENDING), ("ts", ASCENDING)])
    raw_log = db[raw_coll_n] if args.raw else None
    if raw_log is not None:
        raw_log.create_index([("ts", ASCENDING)])

    start_time = utc_now()
    session_id = args.session_id or make_session_id(start_time)
    device_doc = make_device_doc(args, start_time)
    device_update = dict(device_doc)
    device_update.pop("_id", None)
    device_update.pop("created_at", None)
    devices.update_one(
        {"_id": args.device_id},
        {"$set": device_update, "$setOnInsert": {"created_at": start_time}},
        upsert=True,
    )
    sessions.insert_one(make_capture_session_doc(args, session_id, start_time))
    print(f"capture session={session_id} device={args.device_id}", file=sys.stderr)

    enricher = GeminiEnricher(
        api_key=os.environ.get("GOOGLE_API_KEY"),
        model=args.gemini_model,
        enabled=not args.no_gemini,
    )
    window_builder = CsiWindowBuilder(
        session_id=session_id,
        device_id=args.device_id,
        subject_id=args.subject_id,
        activity_name=args.activity_name,
        activity_label_id=args.activity_label_id,
        window_ms=args.sample_window_ms,
    )

    ser = None
    motion_buffer: list[dict[str, Any]] = []
    raw_buffer: list[dict[str, Any]] = []
    sample_buffer: list[dict[str, Any]] = []
    recent_motion_events: list[dict[str, Any]] = []
    n_motion = 0
    n_raw = 0
    n_samples = 0
    last_flush = time.time()
    last_log = 0.0
    buf = b""

    try:
        ser = open_serial(args.port, args.baud)
        print(f"reading {args.port} @ {args.baud}", file=sys.stderr)
        time.sleep(1.5)

        while True:
            buf += ser.read(8192)
            while b"\n" in buf:
                raw_line, _, buf = buf.partition(b"\n")
                text = raw_line.decode("utf-8", errors="ignore").strip()
                ts = utc_now()
                if text.startswith("MOTION,"):
                    parts = text.split(",")
                    if len(parts) != 4:
                        continue
                    try:
                        sid = int(parts[1])
                        score = int(parts[2]) / 1000.0
                        level = int(parts[3])
                    except ValueError:
                        continue
                    event = {
                        "ts": ts,
                        "node": args.node,
                        "device_id": args.device_id,
                        "session_id": session_id,
                        "sender_id": sid,
                        "score": round(score, 4),
                        "level": level,
                        "label": LEVEL_LABEL.get(level, "UNKNOWN"),
                    }
                    motion_buffer.append(event)
                    recent_motion_events.append(event)
                    cutoff = ts.timestamp() - (args.sample_window_ms / 1000.0) * 2
                    recent_motion_events = [
                        item for item in recent_motion_events
                        if item["ts"].timestamp() >= cutoff
                    ]
                elif text.startswith("CSI_DATA"):
                    amp = parse_amplitudes(text)
                    metadata = parse_csi_metadata(text)
                    if amp is None or metadata is None:
                        continue
                    if raw_log is not None:
                        raw_buffer.append({
                            "ts": ts,
                            "node": args.node,
                            "device_id": args.device_id,
                            "session_id": session_id,
                            "seq": metadata["seq"],
                            "mac": metadata["mac"],
                            "sender_id": metadata["sender_id"],
                            "rssi": metadata["rssi"],
                            "n_subcarriers": int(amp.size),
                            "amp_mean": float(amp.mean()),
                        })
                    sample_doc = window_builder.add(ts, amp, metadata, recent_motion_events)
                    if sample_doc is not None:
                        merge_enrichment(sample_doc, enricher.enrich(sample_doc))
                        sample_buffer.append(sample_doc)

            now = time.time()
            if now - last_flush >= args.flush_seconds:
                if motion_buffer:
                    motion_log.insert_many(motion_buffer, ordered=False)
                    n_motion += len(motion_buffer)
                    motion_buffer.clear()
                if raw_buffer and raw_log is not None:
                    raw_log.insert_many(raw_buffer, ordered=False)
                    n_raw += len(raw_buffer)
                    raw_buffer.clear()
                if sample_buffer:
                    sensor_samples.insert_many(sample_buffer, ordered=False)
                    n_samples += len(sample_buffer)
                    sample_buffer.clear()
                last_flush = now

            if now - last_log >= 5.0:
                print(
                    f"[{int(now)}] inserted motion={n_motion} raw={n_raw} samples={n_samples}",
                    file=sys.stderr,
                    flush=True,
                )
                last_log = now
    finally:
        end_time = utc_now()
        pending_sample = window_builder.flush(recent_motion_events)
        if pending_sample is not None:
            merge_enrichment(pending_sample, enricher.enrich(pending_sample))
            sample_buffer.append(pending_sample)
        if motion_buffer:
            motion_log.insert_many(motion_buffer, ordered=False)
        if raw_buffer and raw_log is not None:
            raw_log.insert_many(raw_buffer, ordered=False)
        if sample_buffer:
            sensor_samples.insert_many(sample_buffer, ordered=False)
        sessions.update_one(
            {"_id": session_id},
            {"$set": {"end_time": end_time, "updated_at": end_time}},
        )
        if ser is not None:
            ser.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
