# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.
"""
Stream the receiver's MOTION telemetry to MongoDB Atlas.

The csi_recv firmware emits one line per sender per ~100 ms:
    MOTION,<sender_id>,<score×1000>,<level>
This script parses each line, attaches a UTC timestamp + node id, batches
inserts every --flush-seconds, and writes them to the `motion_log` collection
in your Atlas cluster.

Optionally also stores throttled CSI packet samples in `csi_raw` (use --raw).

Setup:
    cp ../.env.example ../.env       # then edit MONGODB_URI
    python mongo_logger.py            # uses /dev/cu.usbserial-130 by default

The free Atlas M0 tier easily handles a few hundred docs/min — fine for a demo.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient

from csi import open_serial, parse_amplitudes


LEVEL_LABEL = {0: "QUIET", 1: "MOTION", 2: "BUSY"}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/cu.usbserial-130")
    p.add_argument("--baud", type=int, default=921600)
    p.add_argument("--node", default=os.environ.get("CSI_NODE_ID", "rx-01"),
                   help="receiver identifier baked into every doc")
    p.add_argument("--flush-seconds", type=float, default=1.0,
                   help="how often to bulk-insert buffered docs")
    p.add_argument("--raw", action="store_true",
                   help="also log throttled CSI packets to csi_raw")
    args = p.parse_args()

    # Look for .env in repo root, then current dir
    repo_root = Path(__file__).resolve().parent.parent
    for candidate in (repo_root / ".env", Path.cwd() / ".env"):
        if candidate.exists():
            load_dotenv(candidate)
            break

    uri = os.environ.get("MONGODB_URI")
    if not uri or "USER:PASSWORD" in uri or "<" in uri:
        print("error: MONGODB_URI not set in .env (copy .env.example to .env and edit)",
              file=sys.stderr)
        return 2

    db_name      = os.environ.get("MONGODB_DB", "csi_demo")
    motion_coll  = os.environ.get("MONGODB_COLLECTION", "motion_log")
    raw_coll_n   = os.environ.get("MONGODB_RAW_COLLECTION", "csi_raw")

    client = MongoClient(uri, appname="ruview-demo", serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    print(f"connected to atlas → db={db_name}", file=sys.stderr)

    db = client[db_name]
    motion_log = db[motion_coll]
    motion_log.create_index([("ts", ASCENDING)])
    motion_log.create_index([("node", ASCENDING), ("sender_id", ASCENDING), ("ts", ASCENDING)])
    raw_log = db[raw_coll_n] if args.raw else None
    if raw_log is not None:
        raw_log.create_index([("ts", ASCENDING)])

    ser = open_serial(args.port, args.baud)
    print(f"reading {args.port} @ {args.baud}", file=sys.stderr)
    time.sleep(1.5)

    motion_buffer: list[dict] = []
    raw_buffer: list[dict] = []
    n_motion = 0
    n_raw = 0
    last_flush = time.time()
    last_log = 0.0
    buf = b""

    while True:
        buf += ser.read(8192)
        while b"\n" in buf:
            raw_line, _, buf = buf.partition(b"\n")
            text = raw_line.decode("utf-8", errors="ignore").strip()
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
                motion_buffer.append({
                    "ts": datetime.now(tz=timezone.utc),
                    "node": args.node,
                    "sender_id": sid,
                    "score": round(score, 4),
                    "level": level,
                    "label": LEVEL_LABEL.get(level, "UNKNOWN"),
                })
            elif raw_log is not None and text.startswith("CSI_DATA"):
                amp = parse_amplitudes(text)
                if amp is None:
                    continue
                head = text.split(',"')[0].split(",")
                # CSI_DATA,seq,mac,rssi,...
                try:
                    seq = int(head[1])
                    mac = head[2]
                    rssi = int(head[3])
                except (IndexError, ValueError):
                    continue
                raw_buffer.append({
                    "ts": datetime.now(tz=timezone.utc),
                    "node": args.node,
                    "seq": seq,
                    "mac": mac,
                    "sender_id": int(mac.split(":")[-1], 16) if ":" in mac else None,
                    "rssi": rssi,
                    "n_subcarriers": int(amp.size),
                    "amp_mean": float(amp.mean()),
                })

        now = time.time()
        if now - last_flush >= args.flush_seconds:
            if motion_buffer:
                motion_log.insert_many(motion_buffer, ordered=False)
                n_motion += len(motion_buffer)
                motion_buffer.clear()
            if raw_buffer:
                raw_log.insert_many(raw_buffer, ordered=False)
                n_raw += len(raw_buffer)
                raw_buffer.clear()
            last_flush = now

        if now - last_log >= 5.0:
            print(f"[{int(now)}] inserted motion={n_motion} raw={n_raw}",
                  file=sys.stderr, flush=True)
            last_log = now


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
