"""Shared CSI parsing, calibration, and feature extraction."""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass

import numpy as np
import serial

CSI_DATA_RE = re.compile(r'CSI_DATA,.*"\[(?P<data>[^\]]*)\]"')


def open_serial(port: str, baud: int, timeout: float = 0.1) -> serial.Serial:
    """Open a serial port without asserting DTR/RTS.

    Default pyserial behavior asserts both lines when opening, which on many
    CP2102N-based ESP32 dev boards holds the chip in reset (EN low). Setting
    the lines before opening keeps the chip free to run its firmware.
    """
    s = serial.Serial()
    s.port = port
    s.baudrate = baud
    s.timeout = timeout
    s.dtr = False
    s.rts = False
    s.open()
    return s

FEATURE_NAMES = (
    "score_mean",     # mean |z-score| across subcarriers (in-window mean)
    "score_std",      # std of mean |z| over time inside the window
    "score_max",      # max |z-score| over the window
    "frac_high",      # fraction of subcarriers with mean |z| > 3
    "amp_mean",       # mean amplitude (rough power proxy)
    "amp_std",        # time-std of amplitude averaged across subcarriers
)


def parse_amplitudes(line: str) -> np.ndarray | None:
    """Parse a CSI_DATA line, return per-subcarrier amplitudes (zeros dropped)."""
    m = CSI_DATA_RE.search(line)
    if not m:
        return None
    raw = np.fromstring(m.group("data"), sep=",", dtype=np.int16)
    if raw.size < 4 or raw.size % 2:
        return None
    iq = raw.reshape(-1, 2).astype(np.float32)
    amp = np.hypot(iq[:, 0], iq[:, 1])
    amp = amp[amp > 0]  # drop guard / null subcarriers
    return amp if amp.size else None


@dataclass
class Baseline:
    """Per-subcarrier mean and std from empty-room calibration."""
    mean: np.ndarray
    std: np.ndarray
    n_subcarriers: int


def calibrate(ser: serial.Serial, seconds: float, message_stream=sys.stderr) -> Baseline:
    """Read CSI for `seconds`, return per-subcarrier mean and std."""
    print(f"calibrating: keep room empty for {seconds:.0f}s ...", file=message_stream, flush=True)
    samples: list[np.ndarray] = []
    end = time.time() + seconds
    buf = b""
    while time.time() < end:
        buf += ser.read(8192)
        if b"\n" not in buf:
            continue
        chunks = buf.split(b"\n")
        buf = chunks[-1]
        for chunk in chunks[:-1]:
            amp = parse_amplitudes(chunk.decode("utf-8", errors="ignore"))
            if amp is not None:
                samples.append(amp)
    if not samples:
        raise RuntimeError("no CSI samples received during calibration — check sender + receiver are powered on")
    n = min(a.size for a in samples)
    stack = np.stack([a[:n] for a in samples])
    mean = stack.mean(axis=0)
    std = stack.std(axis=0)
    # Floor std to avoid divide-by-zero on subcarriers that happened to be perfectly constant.
    std = np.maximum(std, 1.0)
    print(f"calibration done: {len(samples)} packets, {n} subcarriers", file=message_stream, flush=True)
    return Baseline(mean=mean, std=std, n_subcarriers=n)


def compute_features(window: list[np.ndarray], baseline: Baseline) -> tuple[np.ndarray, float]:
    """Return (feature_vector, presence_score) from a window of amplitude vectors."""
    n = baseline.n_subcarriers
    stack = np.stack([a[:n] for a in window])  # (window, subcarriers)
    z = (stack - baseline.mean) / baseline.std  # per-packet, per-subcarrier z-score
    abs_z = np.abs(z)
    # mean |z| per packet → averaged across subcarriers
    per_packet_mean_z = abs_z.mean(axis=1)  # (window,)
    score_mean = float(per_packet_mean_z.mean())
    score_std = float(per_packet_mean_z.std())
    score_max = float(abs_z.max())
    # fraction of subcarriers with time-mean |z| above 3
    subcarrier_mean_z = abs_z.mean(axis=0)  # (subcarriers,)
    frac_high = float((subcarrier_mean_z > 3.0).mean())
    amp_mean = float(stack.mean())
    amp_std = float(stack.std(axis=0).mean())
    feats = np.array([score_mean, score_std, score_max, frac_high, amp_mean, amp_std],
                     dtype=np.float32)
    return feats, score_mean


def serial_packet_iterator(ser: serial.Serial):
    """Yield per-packet amplitude arrays as they arrive on the serial port."""
    buf = b""
    while True:
        buf += ser.read(8192)
        if b"\n" not in buf:
            continue
        chunks = buf.split(b"\n")
        buf = chunks[-1]
        for chunk in chunks[:-1]:
            amp = parse_amplitudes(chunk.decode("utf-8", errors="ignore"))
            if amp is not None:
                yield amp
