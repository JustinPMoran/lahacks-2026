#!/usr/bin/env python3
# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.
"""Run a local webcam DensePose proof of concept.

Behavior:
- No detected person: display a black frame.
- Detected person: render DensePose or a silhouette on a black frame.
- Original camera pixels are never shown in the output frame.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
DENSEPOSE_PROJECT = REPO_ROOT / "detectron2" / "projects" / "DensePose"
os.environ.setdefault("MPLCONFIGDIR", str(REPO_ROOT / ".cache" / "matplotlib"))
DEFAULT_CONFIG = DENSEPOSE_PROJECT / "configs" / "densepose_rcnn_R_50_FPN_s1x.yaml"
DEFAULT_MODEL = (
    "https://dl.fbaipublicfiles.com/densepose/"
    "densepose_rcnn_R_50_FPN_s1x/165712039/model_final_162be9.pkl"
)

if DENSEPOSE_PROJECT.exists():
    sys.path.insert(0, str(DENSEPOSE_PROJECT))

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
    parser = argparse.ArgumentParser(description="DensePose webcam proof of concept")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="DensePose config path")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="DensePose model URL or path")
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda"), help="Inference device")
    parser.add_argument("--min-score", type=float, default=0.8, help="Minimum person score")
    parser.add_argument(
        "--mode",
        default="densepose",
        choices=("densepose", "silhouette", "u", "v", "contour"),
        help="Output rendering mode",
    )
    parser.add_argument("--width", type=int, default=640, help="Requested capture width")
    parser.add_argument("--height", type=int, default=360, help="Requested capture height")
    parser.add_argument("--flip", action="store_true", help="Mirror the webcam image")
    parser.add_argument("--overlay", action="store_true", help="Draw debug status text on output")
    return parser.parse_args()


def build_predictor(args: argparse.Namespace) -> tuple[DefaultPredictor, object]:
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


def render_densepose(frame: np.ndarray, instances, extractor, visualizer) -> np.ndarray:
    output = np.zeros_like(frame)
    data = extractor(instances)
    return visualizer.visualize(output, data)


def draw_status(frame: np.ndarray, mode: str, found_person: bool, fps: float) -> np.ndarray:
    status = "person" if found_person else "no person"
    text = f"{mode} | {status} | {fps:.1f} fps | q/esc quit"
    cv2.putText(frame, text, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    return frame


def main() -> int:
    args = parse_args()
    predictor, cfg = build_predictor(args)
    visualizer = build_visualizer(args.mode, cfg)
    extractor = DensePoseResultExtractor()

    capture = cv2.VideoCapture(args.camera)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    if not capture.isOpened():
        print(f"Could not open camera index {args.camera}", file=sys.stderr)
        return 1

    window_name = "DensePose Webcam POC"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    last_frame_time = time.perf_counter()
    fps = 0.0

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                print("Camera frame read failed", file=sys.stderr)
                return 1

            if args.flip:
                frame = cv2.flip(frame, 1)
            if frame.shape[1] != args.width or frame.shape[0] != args.height:
                frame = cv2.resize(frame, (args.width, args.height), interpolation=cv2.INTER_AREA)

            start = time.perf_counter()
            with torch.no_grad():
                instances = predictor(frame)["instances"].to("cpu")

            found_person = has_person(instances)
            if not found_person:
                output = np.zeros_like(frame)
            elif args.mode == "silhouette":
                output = render_silhouette(frame, instances)
            else:
                output = render_densepose(frame, instances, extractor, visualizer)

            now = time.perf_counter()
            inference_time = max(now - start, 1e-6)
            frame_interval = max(now - last_frame_time, inference_time)
            fps = 0.9 * fps + 0.1 * (1.0 / frame_interval) if fps else 1.0 / frame_interval
            last_frame_time = now

            if args.overlay:
                output = draw_status(output, args.mode, found_person, fps)
            cv2.imshow(window_name, output)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
