#!/usr/bin/env python3
import argparse
import importlib.util
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch


BACKEND_DIR = Path(__file__).resolve().parent
SERVICE_PATH = BACKEND_DIR / "app" / "services" / "segmentation_service.py"
DEFAULT_IMAGE_PATH = BACKEND_DIR / "tests" / "3.png"
DEFAULT_MODEL_PATH = BACKEND_DIR / "ml_models" / "seg_models" / "upp_model.pth"
DEFAULT_OUTPUT_DIR = BACKEND_DIR / "demo_output"


def load_segmentation_service() -> Any:
    spec = importlib.util.spec_from_file_location("segmentation_service_local", SERVICE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_comparison(original_gray: np.ndarray, label_image: np.ndarray, overlay_image: np.ndarray) -> np.ndarray:
    original_bgr = cv2.cvtColor(original_gray, cv2.COLOR_GRAY2BGR)
    gap = np.full((original_bgr.shape[0], 16, 3), 255, dtype=np.uint8)
    return cv2.hconcat([original_bgr, gap, label_image, gap, overlay_image])


def main() -> None:
    parser = argparse.ArgumentParser(description="影像分割模块 overlay 演示")
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE_PATH, help="输入胸片路径")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help="分割模型权重路径")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="输出目录")
    args = parser.parse_args()

    seg = load_segmentation_service()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    original_gray = cv2.imread(str(args.image), cv2.IMREAD_GRAYSCALE)
    if original_gray is None:
        raise RuntimeError(f"无法读取输入影像: {args.image}")

    model = seg.load_model(str(args.model))
    tensor = seg.preprocess(str(args.image))

    with torch.no_grad():
        prediction = model(tensor)

    artifacts = seg.build_segmentation_artifacts(prediction, original_gray)

    stem = args.image.stem
    model_stem = args.model.stem
    overlay_path = args.output_dir / f"{stem}_{model_stem}_overlay.png"
    label_path = args.output_dir / f"{stem}_{model_stem}_label.png"
    comparison_path = args.output_dir / f"{stem}_{model_stem}_comparison.png"
    visualization_path = args.output_dir / f"{stem}_{model_stem}_visualization.png"

    cv2.imwrite(str(overlay_path), artifacts["overlay_image"])
    cv2.imwrite(str(label_path), artifacts["label_image"])
    cv2.imwrite(str(visualization_path), artifacts["visualization_sample_image"])
    cv2.imwrite(
        str(comparison_path),
        build_comparison(original_gray, artifacts["label_image"], artifacts["overlay_image"]),
    )

    print(f"input_image: {args.image}")
    print(f"model_path: {args.model}")
    print(f"overlay_image: {overlay_path}")
    print(f"label_image: {label_path}")
    print(f"comparison_image: {comparison_path}")
    print(f"visualization_image: {visualization_path}")
    print(f"mean_confidence: {artifacts['mean_confidence']:.4f}")
    print(f"right_lung_area: {artifacts['right_lung_area']:.0f}")
    print(f"left_lung_area: {artifacts['left_lung_area']:.0f}")
    print(f"heart_area: {artifacts['heart_area']:.0f}")
    print(f"cardiothoracic_ratio: {artifacts['cardiothoracic_ratio']:.4f}")


if __name__ == "__main__":
    main()
