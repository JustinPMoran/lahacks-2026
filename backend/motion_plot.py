"""
Headless motion logger: read MOTION lines from the receiver C6 over serial,
print human-readable per-sender events, and append them as JSONL to a local
file that the frontend tails.

    python motion_plot.py                       # macbook default port
    python motion_plot.py --port /dev/ttyUSB0   # raspberry pi

Default log path: /tmp/ruview_motion.jsonl (override with --log-file or
RUVIEW_MOTION_LOG).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from csi import open_serial


LEVEL_LABEL = {0: "QUIET", 1: "MOTION", 2: "BUSY"}
DEFAULT_LOG_PATH = os.environ.get("RUVIEW_MOTION_LOG", "/tmp/ruview_motion.jsonl")


class FileSink:
    """Append motion events as JSONL to a local file. The frontend tails
    the same file. Truncates on startup so each session starts clean."""

    def __init__(self, node: str, path: str = DEFAULT_LOG_PATH):
        self.node = node
        self.path = path
        try:
            self._fh = open(path, "w", buffering=1)  # line-buffered
            print(f"motion log: writing to {path}", file=sys.stderr)
        except OSError as e:
            print(f"motion log: open failed ({e}) — disabling sink", file=sys.stderr)
            self._fh = None

    def push(self, sender_id: int, score: float, level: int) -> None:
        if self._fh is None:
            return
        doc = {
            "ts": time.time(),
            "node": self.node,
            "sender_id": sender_id,
            "score": round(score, 4),
            "level": level,
            "label": LEVEL_LABEL.get(level, "UNKNOWN"),
        }
        try:
            self._fh.write(json.dumps(doc) + "\n")
        except OSError as e:
            print(f"motion log: write failed ({e})", file=sys.stderr)
            self._fh = None


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/cu.usbserial-110")
    p.add_argument("--baud", type=int, default=921600)
    p.add_argument("--node", default=os.environ.get("CSI_NODE_ID", "rx-01"),
                   help="receiver node id baked into log entries")
    p.add_argument("--summary-interval", type=float, default=2.0,
                   help="seconds between periodic per-sender status summary lines")
    p.add_argument("--log-file", default=DEFAULT_LOG_PATH,
                   help="JSONL motion log path (frontend tails this file)")
    p.add_argument("--no-log", action="store_true",
                   help="disable file logging entirely")
    args = p.parse_args()

    sink = None if args.no_log else FileSink(args.node, args.log_file)

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
