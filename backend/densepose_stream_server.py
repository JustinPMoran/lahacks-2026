#!/usr/bin/env python3
# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.
"""Run a GPU DensePose WebSocket inference server.

Protocol:
- Client sends one JPEG-encoded camera frame as a binary WebSocket message.
- Server replies with one JPEG-encoded rendered DensePose frame.

This is intended for the live deployment loop:
Raspberry Pi camera/frontend -> RunPod GPU -> frontend live DensePose panel.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import websockets


REPO_ROOT = Path(__file__).resolve().parents[1]
DENSEPOSE_PROJECT = REPO_ROOT / "detectron2" / "projects" / "DensePose"
LOCAL_MODEL = REPO_ROOT / "models" / "densepose_rcnn_R_50_FPN_s1x_model_final_162be9.pkl"
DEFAULT_CONFIG = DENSEPOSE_PROJECT / "configs" / "densepose_rcnn_R_50_FPN_s1x.yaml"
DEFAULT_MODEL = (
    str(LOCAL_MODEL)
    if LOCAL_MODEL.exists()
    else "https://dl.fbaipublicfiles.com/densepose/"
    "densepose_rcnn_R_50_FPN_s1x/165712039/model_final_162be9.pkl"
)

os.environ.setdefault("MPLCONFIGDIR", str(REPO_ROOT / ".cache" / "matplotlib"))

if DENSEPOSE_PROJECT.exists():
    sys.path.insert(0, str(DENSEPOSE_PROJECT))

try:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
except ImportError:
    FigureCanvasAgg = None

if FigureCanvasAgg is not None and not hasattr(FigureCanvasAgg, "tostring_rgb"):
    def _figure_canvas_agg_tostring_rgb(self):
        self.draw()
        rgba = np.asarray(self.buffer_rgba())
        return rgba[:, :, :3].tobytes()

    FigureCanvasAgg.tostring_rgb = _figure_canvas_agg_tostring_rgb

from detectron2.config import get_cfg  # noqa: E402
from detectron2.engine.defaults import DefaultPredictor  # noqa: E402
from densepose import add_densepose_config  # noqa: E402
import densepose.converters.builtin  # noqa: F401,E402
from densepose.converters import ToMaskConverter  # noqa: E402
from densepose.vis.densepose_results import (  # noqa: E402
    DensePoseResultsContourVisualizer,
    DensePoseResultsFineSegmentationVisualizer,
    DensePoseResultsUVisualizer,
    DensePoseResultsVVisualizer,
)
from densepose.vis.extractor import DensePoseResultExtractor  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DensePose GPU WebSocket stream server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket port")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="DensePose config path")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="DensePose model URL or local path")
    parser.add_argument("--device", default="cuda", choices=("cpu", "cuda"), help="Inference device")
    parser.add_argument("--min-score", type=float, default=0.8, help="Minimum person score")
    parser.add_argument(
        "--mode",
        default="mesh_fast",
        choices=("densepose", "mesh_fast", "mesh", "silhouette", "u", "v", "contour"),
        help="Rendered response mode; mesh_fast avoids Matplotlib for higher FPS",
    )
    parser.add_argument("--max-width", type=int, default=512, help="Resize incoming frames above this width")
    parser.add_argument("--jpeg-quality", type=int, default=70, help="Response JPEG quality")
    parser.add_argument("--max-message-bytes", type=int, default=8_000_000, help="Maximum inbound frame size")
    return parser.parse_args()


def build_predictor(args: argparse.Namespace) -> tuple[DefaultPredictor, object]:
    if args.device == "cuda":
        torch.backends.cudnn.benchmark = True
    cfg = get_cfg()
    add_densepose_config(cfg)
    cfg.merge_from_file(args.config)
    cfg.MODEL.WEIGHTS = args.model
    cfg.MODEL.DEVICE = args.device
    cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = args.min_score
    cfg.freeze()
    return DefaultPredictor(cfg), cfg


def build_visualizer(mode: str, cfg: object):
    if mode == "silhouette":
        return None
    if mode == "mesh_fast":
        return ("mesh_fast", DensePoseResultsFineSegmentationVisualizer(cfg=cfg, alpha=1.0))
    if mode == "mesh":
        return (
            DensePoseResultsFineSegmentationVisualizer(cfg=cfg, alpha=1.0),
            DensePoseResultsContourVisualizer(),
        )
    if mode == "u":
        return DensePoseResultsUVisualizer(cfg=cfg, alpha=1.0)
    if mode == "v":
        return DensePoseResultsVVisualizer(cfg=cfg, alpha=1.0)
    if mode == "contour":
        return DensePoseResultsContourVisualizer()
    return DensePoseResultsFineSegmentationVisualizer(cfg=cfg, alpha=1.0)


def has_person(instances) -> bool:
    return len(instances) > 0 and instances.has("pred_densepose") and instances.has("pred_boxes")


def render_silhouette(frame: np.ndarray, instances) -> np.ndarray:
    output = np.zeros_like(frame)
    masks = ToMaskConverter.convert(instances.pred_densepose, instances.pred_boxes, frame.shape[:2])
    person_mask = masks.tensor.any(dim=0).cpu().numpy().astype(bool)
    output[person_mask] = (255, 255, 255)
    return output


def overlay_fast_mesh(output: np.ndarray) -> np.ndarray:
    mask = np.any(output > 0, axis=2).astype(np.uint8)
    if not mask.any():
        return output

    edges = cv2.Canny(mask * 255, 50, 150) > 0
    output[edges] = (255, 255, 255)

    # Draw a lightweight screen-space mesh clipped to the detected body.
    mesh = np.zeros_like(output)
    step = max(12, output.shape[1] // 28)
    mesh[:, ::step] = (0, 255, 255)
    mesh[::step, :] = (0, 255, 180)
    mesh_mask = mask.astype(bool)
    output[mesh_mask] = cv2.addWeighted(output, 0.82, mesh, 0.18, 0)[mesh_mask]
    return output


def render_densepose(frame: np.ndarray, instances, extractor, visualizer) -> np.ndarray:
    output = np.zeros_like(frame)
    data = extractor(instances)
    if isinstance(visualizer, tuple) and visualizer[0] == "mesh_fast":
        output = visualizer[1].visualize(output, data)
        return overlay_fast_mesh(output)
    if isinstance(visualizer, tuple):
        for layer in visualizer:
            output = layer.visualize(output, data)
        return output
    return visualizer.visualize(output, data)


class DensePoseStreamServer:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.predictor, self.cfg = build_predictor(args)
        self.visualizer = build_visualizer(args.mode, self.cfg)
        self.extractor = DensePoseResultExtractor()
        self.frame_count = 0
        self.last_log_time = time.perf_counter()

    def process_jpeg(self, payload: bytes) -> bytes:
        encoded = np.frombuffer(payload, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("could not decode JPEG frame")

        if self.args.max_width and frame.shape[1] > self.args.max_width:
            scale = self.args.max_width / frame.shape[1]
            height = int(frame.shape[0] * scale)
            frame = cv2.resize(frame, (self.args.max_width, height), interpolation=cv2.INTER_AREA)

        with torch.inference_mode():
            instances = self.predictor(frame)["instances"].to("cpu")

        if not has_person(instances):
            output = np.zeros_like(frame)
        elif self.args.mode == "silhouette":
            output = render_silhouette(frame, instances)
        else:
            output = render_densepose(frame, instances, self.extractor, self.visualizer)

        ok, response = cv2.imencode(".jpg", output, [cv2.IMWRITE_JPEG_QUALITY, self.args.jpeg_quality])
        if not ok:
            raise RuntimeError("could not encode response JPEG")

        self.frame_count += 1
        now = time.perf_counter()
        elapsed = now - self.last_log_time
        if elapsed >= 5.0:
            print(f"processed {self.frame_count / elapsed:.1f} fps", flush=True)
            self.frame_count = 0
            self.last_log_time = now

        return response.tobytes()

    async def handle_connection(self, websocket) -> None:
        peer = getattr(websocket, "remote_address", "unknown")
        print(f"client connected: {peer}", flush=True)
        try:
            async for message in websocket:
                if not isinstance(message, bytes):
                    await websocket.send("send JPEG frames as binary WebSocket messages")
                    continue

                try:
                    response = self.process_jpeg(message)
                except Exception as exc:  # Keep the stream alive across bad frames.
                    print(f"frame error: {exc}", file=sys.stderr, flush=True)
                    await websocket.send(f"error: {exc}")
                    continue

                await websocket.send(response)
        finally:
            print(f"client disconnected: {peer}", flush=True)


async def serve(args: argparse.Namespace) -> None:
    server = DensePoseStreamServer(args)
    print(f"DensePose stream server listening on ws://{args.host}:{args.port}", flush=True)
    async with websockets.serve(
        server.handle_connection,
        args.host,
        args.port,
        max_size=args.max_message_bytes,
        compression=None,
    ):
        await asyncio.Future()


def main() -> int:
    args = parse_args()
    if args.device == "cuda" and not torch.cuda.is_available():
        print("CUDA was requested but is not available", file=sys.stderr)
        return 1
    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
