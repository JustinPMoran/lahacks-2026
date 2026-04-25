"""Live monitor for the receiver firmware's MOTION,score_millis,level lines.

Just listens, prints each update as it arrives, and shows a bar so you can
eyeball motion at a glance. Use to verify firmware-side detection without
recomputing the score in Python.

    python motion_monitor.py --port /dev/cu.usbserial-130
"""

from __future__ import annotations

import argparse
import sys
import time

from csi import open_serial


COLORS = {0: "\x1b[32m", 1: "\x1b[33m", 2: "\x1b[31m"}
RESET = "\x1b[0m"
LABELS = {0: "QUIET", 1: "MOTION", 2: "BUSY"}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/cu.usbserial-130")
    p.add_argument("--baud", type=int, default=921600)
    p.add_argument("--bar-scale", type=float, default=8.0,
                   help="characters per unit of score in the bar")
    p.add_argument("--bar-max", type=int, default=60)
    args = p.parse_args()

    ser = open_serial(args.port, args.baud)
    print(f"reading {args.port} @ {args.baud}", file=sys.stderr)
    time.sleep(1.5)
    print(f"   t      score  level   bar")
    print(f"-------- -------  -----  {'-' * args.bar_max}")

    buf = b""
    t0 = time.time()
    while True:
        buf += ser.read(8192)
        while b"\n" in buf:
            line, _, buf = buf.partition(b"\n")
            text = line.decode("utf-8", errors="ignore").strip()
            if not text.startswith("MOTION,"):
                continue
            try:
                _, ms, lvl = text.split(",")
                score = int(ms) / 1000.0
                level = int(lvl)
            except ValueError:
                continue
            bar_len = min(args.bar_max, int(score * args.bar_scale))
            color = COLORS.get(level, "")
            print(f"{time.time()-t0:7.1f}s  {score:6.3f}    {level}    "
                  f"{color}{'#' * bar_len}{RESET}", flush=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
