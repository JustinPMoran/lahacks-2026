"""
MATLAB-style live dashboard, per-sender.

Top panel    : motion score for each sender (one line per source MAC byte) over
               time, with green/yellow/red threshold bands and a per-sender
               state label.
Bottom panel : CSI amplitude waterfall — subcarrier (y) × time (x), color = amp.
               Vertical streaks = motion perturbing the channel.

    python motion_plot.py --port /dev/cu.usbserial-130
"""

from __future__ import annotations

import argparse
import collections
import sys
import time

import matplotlib

matplotlib.use("macosx")
import matplotlib.pyplot as plt
import numpy as np

from csi import open_serial, parse_amplitudes


SENDER_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/cu.usbserial-130")
    p.add_argument("--baud", type=int, default=921600)
    p.add_argument("--score-history", type=int, default=600)
    p.add_argument("--csi-history", type=int, default=300)
    p.add_argument("--quiet-thresh", type=float, default=1.5)
    p.add_argument("--busy-thresh", type=float, default=4.0)
    args = p.parse_args()

    ser = open_serial(args.port, args.baud)
    print(f"reading {args.port} @ {args.baud}", file=sys.stderr)
    time.sleep(1.5)

    # Per-sender state
    sender_t: dict[int, collections.deque[float]] = {}
    sender_y: dict[int, collections.deque[float]] = {}
    sender_lvl: dict[int, int] = {}
    sender_lines: dict[int, plt.Line2D] = {}
    waterfall: collections.deque[np.ndarray] = collections.deque(maxlen=args.csi_history)

    plt.ion()
    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(11, 7),
                                         gridspec_kw={"height_ratios": [1, 1.4]})
    fig.canvas.manager.set_window_title("CSI per-sender motion dashboard")

    ax_top.axhspan(0, args.quiet_thresh, alpha=0.10, color="green")
    ax_top.axhspan(args.quiet_thresh, args.busy_thresh, alpha=0.10, color="orange")
    ax_top.axhspan(args.busy_thresh, args.busy_thresh + 10, alpha=0.10, color="red")
    ax_top.axhline(args.quiet_thresh, color="orange", lw=1, ls="--")
    ax_top.axhline(args.busy_thresh, color="red", lw=1, ls="--")
    state_label = ax_top.text(0.02, 0.95, "", transform=ax_top.transAxes,
                              fontsize=12, fontweight="bold", va="top",
                              family="monospace")
    ax_top.set_xlabel("time (s)")
    ax_top.set_ylabel("motion score per sender")
    ax_top.set_title("Per-sender motion — one curve per source MAC")
    ax_top.grid(True, alpha=0.3)

    placeholder = np.zeros((1, args.csi_history))
    img = ax_bot.imshow(placeholder, aspect="auto", origin="lower",
                        cmap="viridis", vmin=0, vmax=64,
                        extent=(-args.csi_history, 0, 0, 1))
    ax_bot.set_xlabel("packets ago (newest at right, all senders combined)")
    ax_bot.set_ylabel("subcarrier")
    ax_bot.set_title("CSI amplitude waterfall")
    plt.colorbar(img, ax=ax_bot, label="amplitude")
    fig.tight_layout()

    t0 = time.time()
    last_draw = 0.0
    buf = b""

    while True:
        buf += ser.read(8192)
        while b"\n" in buf:
            raw_line, _, buf = buf.partition(b"\n")
            line_text = raw_line.decode("utf-8", errors="ignore").strip()
            if line_text.startswith("MOTION,"):
                parts = line_text.split(",")
                # format: MOTION,sender_id,score_milli,level
                if len(parts) != 4:
                    continue
                try:
                    sid = int(parts[1])
                    score = int(parts[2]) / 1000.0
                    level = int(parts[3])
                except ValueError:
                    continue
                if sid not in sender_t:
                    sender_t[sid] = collections.deque(maxlen=args.score_history)
                    sender_y[sid] = collections.deque(maxlen=args.score_history)
                    color = SENDER_COLORS[len(sender_lines) % len(SENDER_COLORS)]
                    (ln,) = ax_top.plot([], [], lw=2, color=color,
                                        label=f"sender 0x{sid:02x}")
                    sender_lines[sid] = ln
                    ax_top.legend(loc="upper right")
                sender_t[sid].append(time.time() - t0)
                sender_y[sid].append(score)
                sender_lvl[sid] = level
            elif line_text.startswith("CSI_DATA"):
                amp = parse_amplitudes(line_text)
                if amp is not None:
                    waterfall.append(amp)

        now = time.time()
        if now - last_draw >= 0.2 and sender_t:
            tmax = max(t[-1] for t in sender_t.values() if t)
            for sid, ln in sender_lines.items():
                if sender_t[sid]:
                    ln.set_data(sender_t[sid], sender_y[sid])
            ax_top.set_xlim(max(0, tmax - 30), tmax + 0.5)
            ymax = max((max(y) for y in sender_y.values() if y), default=4.0)
            ax_top.set_ylim(0, max(ymax * 1.2, args.busy_thresh * 1.2))

            # State label: per-sender current score and level
            label_lines = []
            for sid in sorted(sender_t.keys()):
                if not sender_y[sid]:
                    continue
                score = sender_y[sid][-1]
                level = sender_lvl.get(sid, 0)
                state = {0: "QUIET", 1: "MOTION", 2: "BUSY"}[level]
                label_lines.append(f"0x{sid:02x}  {score:5.2f}  {state}")
            state_label.set_text("\n".join(label_lines))

            if waterfall:
                n = min(a.size for a in waterfall)
                w = np.stack([a[:n] for a in waterfall]).T
                if w.shape[1] < args.csi_history:
                    pad = np.zeros((n, args.csi_history - w.shape[1]))
                    w = np.concatenate([pad, w], axis=1)
                img.set_data(w)
                img.set_extent((-w.shape[1], 0, 0, n))
                img.set_clim(vmin=0, vmax=max(8, float(w.max())))
                ax_bot.set_ylim(0, n)

            fig.canvas.draw_idle()
            fig.canvas.flush_events()
            last_draw = now


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
