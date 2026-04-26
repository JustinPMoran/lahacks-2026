"""
Headless motion logger: read MOTION lines from the receiver C6 over serial,
print human-readable per-sender events, and stream them to MongoDB.

    python motion_plot.py                       # macbook default port
    python motion_plot.py --port /dev/ttyUSB0   # raspberry pi
"""

from __future__ import annotations

import argparse
import os
import queue
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from csi import open_serial


LEVEL_LABEL = {0: "QUIET", 1: "MOTION", 2: "BUSY"}


class MongoSink:
    """Background writer for motion docs. No-op if pymongo / dotenv missing,
    or MONGODB_URI not set. Never blocks the read loop."""

    def __init__(self, node: str, flush_seconds: float = 1.0):
        self.node = node
        self.flush_seconds = flush_seconds
        self.q: queue.Queue[dict] = queue.Queue(maxsize=10000)
        self._coll = None
        self._stopped = threading.Event()

        try:
            import certifi
            from dotenv import load_dotenv
            from pymongo import ASCENDING, MongoClient
        except ImportError:
            print("mongo: pymongo/python-dotenv/certifi not installed — skipping logging",
                  file=sys.stderr)
            return

        for d in (Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent):
            if (d / ".env").exists():
                load_dotenv(d / ".env")
                break

        uri = os.environ.get("MONGODB_URI")
        if not uri or "USER:PASSWORD" in uri or "<" in uri:
            print("mongo: MONGODB_URI not set — skipping logging", file=sys.stderr)
            return

        try:
            client = MongoClient(uri, appname="ruview-demo",
                                 tls=True, tlsCAFile=certifi.where(),
                                 serverSelectionTimeoutMS=5000)
            client.admin.command("ping")
        except Exception as e:
            err = str(e).splitlines()[0][:120]
            print(f"mongo: connection failed, skipping logging ({err})", file=sys.stderr)
            return

        db = client[os.environ.get("MONGODB_DB", "csi_demo")]
        coll = db[os.environ.get("MONGODB_COLLECTION", "motion_log")]
        coll.create_index([("ts", ASCENDING)])
        coll.create_index([("node", ASCENDING), ("sender_id", ASCENDING), ("ts", ASCENDING)])
        self._coll = coll
        threading.Thread(target=self._run, daemon=True).start()
        print(f"mongo: logging to {db.name}.{coll.name}", file=sys.stderr)

    def push(self, sender_id: int, score: float, level: int) -> None:
        if self._coll is None:
            return
        doc = {
            "ts": datetime.now(tz=timezone.utc),
            "node": self.node,
            "sender_id": sender_id,
            "score": round(score, 4),
            "level": level,
            "label": LEVEL_LABEL.get(level, "UNKNOWN"),
        }
        try:
            self.q.put_nowait(doc)
        except queue.Full:
            pass

    def _run(self) -> None:
        buf: list[dict] = []
        last_flush = time.time()
        while not self._stopped.is_set():
            try:
                buf.append(self.q.get(timeout=self.flush_seconds))
            except queue.Empty:
                pass
            now = time.time()
            if buf and (now - last_flush) >= self.flush_seconds:
                try:
                    res = self._coll.insert_many(buf, ordered=False)
                    print(f"mongo: wrote {len(res.inserted_ids)} docs to "
                          f"{self._coll.database.name}.{self._coll.name}",
                          file=sys.stderr)
                except Exception as e:
                    print(f"mongo: insert failed: {e}", file=sys.stderr)
                buf.clear()
                last_flush = now


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/cu.usbserial-110")
    p.add_argument("--baud", type=int, default=921600)
    p.add_argument("--node", default=os.environ.get("CSI_NODE_ID", "rx-01"),
                   help="receiver node id baked into mongo docs")
    p.add_argument("--summary-interval", type=float, default=2.0,
                   help="seconds between periodic per-sender status summary lines")
    p.add_argument("--no-mongo", action="store_true",
                   help="disable MongoDB logging even if MONGODB_URI is set")
    args = p.parse_args()

    sink = MongoSink(args.node) if not args.no_mongo else None

    ser = open_serial(args.port, args.baud)
    print(f"reading {args.port} @ {args.baud}", file=sys.stderr)

    sender_score: dict[int, float] = {}
    sender_lvl: dict[int, int] = {}
    last_summary = 0.0
    buf = b""

    while True:
        buf += ser.read(8192)
        while b"\n" in buf:
            raw, _, buf = buf.partition(b"\n")
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line.startswith("MOTION,"):
                continue
            parts = line.split(",")
            if len(parts) != 4:
                continue
            try:
                sid = int(parts[1])
                score = int(parts[2]) / 1000.0
                level = int(parts[3])
            except ValueError:
                continue

            if sid not in sender_lvl:
                print(f"[{_ts()}] sender 0x{sid:02x} registered "
                      f"(score={score:.2f}, level={LEVEL_LABEL[level]})", flush=True)
            elif sender_lvl[sid] != level:
                print(f"[{_ts()}] sender 0x{sid:02x}: "
                      f"{LEVEL_LABEL[sender_lvl[sid]]} → {LEVEL_LABEL[level]} "
                      f"(score={score:.2f})", flush=True)

            sender_score[sid] = score
            sender_lvl[sid] = level

            if sink is not None:
                sink.push(sid, score, level)

        now = time.time()
        if now - last_summary >= args.summary_interval and sender_score:
            cells = "  ".join(
                f"0x{sid:02x}={sender_score[sid]:5.2f} {LEVEL_LABEL[sender_lvl[sid]]}"
                for sid in sorted(sender_score)
            )
            print(f"[{_ts()}] {cells}", flush=True)
            last_summary = now


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
