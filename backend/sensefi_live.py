# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.
"""
Live CSI -> SenseFi inference for the brand-new ESP32-S3.

Pipeline:
    S3 (esp-csi csi_recv firmware) --serial--> CSI_DATA lines
    -> sliding window of 250 packets, each padded/truncated to 90 subcarriers
    -> (1, 1, 250, 90) float32 tensor
    -> SenseFi UT_HAR_LeNet (or any UT-HAR model class)
    -> argmax + softmax
    -> /tmp/ruview_sensing.jsonl (same JSONL bus as motion_plot.py)

Without a trained --checkpoint this is a pipeline smoke test: predictions
are noise. Once you collect labeled windows + train, drop the .pt path in
and the same loop produces real activity classifications.

Flash the S3 first (one-time, brand-new chip):
    cd vendor/esp-csi/examples/get-started/csi_recv
    . ~/esp/esp-idf/export.sh           # adjust to your IDF install
    idf.py set-target esp32s3
    idf.py build
    idf.py -p /dev/ttyACM0 flash monitor   # Ctrl-] to exit monitor

Then on the Pi:
    pip install torch torchvision scipy einops
    python backend/sensefi_live.py --port /dev/ttyACM0
    python backend/sensefi_live.py --port /dev/ttyACM0 --checkpoint weights/lenet.pt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import deque

import numpy as np

# Vendor SenseFi onto sys.path so we can import its model classes directly.
_SENSEFI = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "vendor", "sensefi"
))
if _SENSEFI not in sys.path:
    sys.path.insert(0, _SENSEFI)

import torch  # noqa: E402
from UT_HAR_model import UT_HAR_LeNet  # noqa: E402

from csi import open_serial, serial_packet_iterator  # noqa: E402


UT_HAR_CLASSES = ["lie down", "fall", "walk", "pickup", "run", "sit down", "stand up"]
DEFAULT_LOG_PATH = os.environ.get("RUVIEW_SENSING_LOG", "/tmp/ruview_sensing.jsonl")
WINDOW_PACKETS = 250
MODEL_SUBCARRIERS = 90


def fit_packet(amp: np.ndarray) -> np.ndarray:
    """Pad / truncate one CSI packet's amplitude vector to MODEL_SUBCARRIERS."""
    if amp.size >= MODEL_SUBCARRIERS:
        return amp[:MODEL_SUBCARRIERS].astype(np.float32)
    out = np.zeros(MODEL_SUBCARRIERS, dtype=np.float32)
    out[:amp.size] = amp.astype(np.float32)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyACM0",
                   help="serial port the ESP32-S3 enumerated as (often /dev/ttyACM0 for native USB)")
    p.add_argument("--baud", type=int, default=921600)
    p.add_argument("--checkpoint", default=None,
                   help="optional .pt weights for UT_HAR_LeNet — random init otherwise")
    p.add_argument("--log-file", default=DEFAULT_LOG_PATH)
    p.add_argument("--stride", type=int, default=25,
                   help="run inference every N new packets (default 25; ~4 Hz at 100 pkt/s)")
    p.add_argument("--device", default=None, help="torch device override (cpu / cuda / mps)")
    args = p.parse_args()

    if args.device:
        device = torch.device(args.device)
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")

    model = UT_HAR_LeNet().to(device)
    if args.checkpoint:
        state = torch.load(args.checkpoint, map_location=device)
        model.load_state_dict(state if isinstance(state, dict) and "fc.0.weight" in state else state)
        print(f"loaded checkpoint: {args.checkpoint}", file=sys.stderr)
    else:
        print("WARNING: no --checkpoint — predictions are random until you train one",
              file=sys.stderr)
    model.eval()

    log_fh = open(args.log_file, "w", buffering=1)
    print(f"writing predictions to {args.log_file}", file=sys.stderr)

    ser = open_serial(args.port, args.baud)
    print(f"reading {args.port} @ {args.baud} on {device}", file=sys.stderr)

    window: deque[np.ndarray] = deque(maxlen=WINDOW_PACKETS)
    since_last = 0
    packet_count = 0
    t0 = time.time()

    for amp in serial_packet_iterator(ser):
        window.append(fit_packet(amp))
        packet_count += 1
        since_last += 1
        if len(window) < WINDOW_PACKETS or since_last < args.stride:
            continue
        since_last = 0

        x = np.stack(window, axis=0)                                # (250, 90)
        # per-subcarrier z-norm so absolute amplitude scale is irrelevant
        mu = x.mean(axis=0, keepdims=True)
        sd = x.std(axis=0, keepdims=True) + 1e-6
        x = (x - mu) / sd
        tensor = torch.from_numpy(x[None, None, :, :]).float().to(device)
        with torch.no_grad():
            logits = model(tensor)
            probs = torch.softmax(logits, dim=-1)[0].cpu().numpy()
        cls = int(probs.argmax())

        rate = packet_count / max(1e-6, time.time() - t0)
        log_fh.write(json.dumps({
            "ts": time.time(),
            "model": "UT_HAR_LeNet",
            "cls_idx": cls,
            "cls_label": UT_HAR_CLASSES[cls],
            "confidence": round(float(probs[cls]), 4),
            "probs": [round(float(pi), 4) for pi in probs],
            "packet_rate_hz": round(rate, 1),
            "trained": bool(args.checkpoint),
        }) + "\n")
        print(f"[{packet_count:>6}] {UT_HAR_CLASSES[cls]:<10} "
              f"p={probs[cls]:.2f}  rate={rate:.0f} Hz", flush=True)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
