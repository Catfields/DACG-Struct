#!/usr/bin/env python3
import argparse
import importlib.util
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch


BACKEND_DIR = Path(__file__).resolve().parents[1]
SERVICE_PATH = BACKEND_DIR / 'app' / 'services' / 'segmentation_service.py'
DEFAULT_MODEL_PATH = BACKEND_DIR / 'ml_models' / 'unet.pth'
DEFAULT_IMAGE_PATH = BACKEND_DIR / 'tests' / '2.png'
DEFAULT_OUTPUT_DIR = BACKEND_DIR / 'tests' / 'output'


CLASS_ORDER = [
    (1, 'right_lung'),
    (2, 'left_lung'),
    (3, 'heart'),
]


def load_segmentation_service() -> Any:
    spec = importlib.util.spec_from_file_location('segmentation_service_local', SERVICE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def add_title(image: np.ndarray, title: str) -> np.ndarray:
    canvas = np.full((image.shape[0] + 48, image.shape[1], 3), 255, dtype=np.uint8)
    canvas[48:] = image
    cv2.putText(canvas, title, (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (32, 32, 32), 2, cv2.LINE_AA)
    return canvas


def save_comparison(output_dir: Path, stem: str, original_gray: np.ndarray, artifacts: dict[str, Any]) -> Path:
    original_bgr = cv2.cvtColor(original_gray, cv2.COLOR_GRAY2BGR)
    panels = [
        add_title(original_bgr, 'Original'),
        add_title(artifacts['label_image'], 'Pred Mask'),
        add_title(artifacts['overlay_image'], 'Overlay'),
    ]
    comparison = cv2.hconcat(panels)
    comparison_path = output_dir / f'{stem}_comparison.png'
    cv2.imwrite(str(comparison_path), comparison)
    return comparison_path


def load_ground_truth(gt_path: Path, label_shape: tuple[int, int]) -> np.ndarray:
    gt = cv2.imread(str(gt_path), cv2.IMREAD_UNCHANGED)
    if gt is None:
        raise RuntimeError(f'无法读取真值掩膜: {gt_path}')

    if gt.ndim == 3:
        gt = cv2.cvtColor(gt, cv2.COLOR_BGR2GRAY)

    gt = cv2.resize(gt, (label_shape[1], label_shape[0]), interpolation=cv2.INTER_NEAREST)
    unique_vals = set(int(v) for v in np.unique(gt))

    if unique_vals.issubset({0, 1, 2, 3}):
        return gt.astype(np.uint8)

    if unique_vals.issubset({0, 85, 170, 255}):
        mapping = {0: 0, 85: 1, 170: 2, 255: 3}
        remapped = np.zeros_like(gt, dtype=np.uint8)
        for src, dst in mapping.items():
            remapped[gt == src] = dst
        return remapped

    raise RuntimeError(
        '真值掩膜标签不受支持。当前只支持标签值 {0,1,2,3} 或 {0,85,170,255}。'
    )


def compute_supervised_metrics(pred_labels: np.ndarray, gt_labels: np.ndarray) -> dict[str, Any]:
    results: dict[str, Any] = {}
    class_rows = []
    dice_values = []
    iou_values = []

    for class_id, class_name in CLASS_ORDER:
        pred_mask = pred_labels == class_id
        gt_mask = gt_labels == class_id
        inter = float(np.logical_and(pred_mask, gt_mask).sum())
        pred_area = float(pred_mask.sum())
        gt_area = float(gt_mask.sum())
        union = pred_area + gt_area - inter

        precision = inter / pred_area if pred_area > 0 else 0.0
        recall = inter / gt_area if gt_area > 0 else 0.0
        dice = (2.0 * inter) / (pred_area + gt_area) if (pred_area + gt_area) > 0 else 0.0
        iou = inter / union if union > 0 else 0.0

        dice_values.append(dice)
        iou_values.append(iou)
        class_rows.append({
            'class_name': class_name,
            'precision': precision,
            'recall': recall,
            'dice': dice,
            'iou': iou,
            'pred_area': pred_area,
            'gt_area': gt_area,
        })

    results['per_class'] = class_rows
    results['mean_dice'] = float(np.mean(dice_values)) if dice_values else 0.0
    results['mean_iou'] = float(np.mean(iou_values)) if iou_values else 0.0
    results['pixel_accuracy'] = float((pred_labels == gt_labels).mean())
    return results


def print_pred_metrics(artifacts: dict[str, Any]) -> None:
    print('预测统计:')
    print(f"- mean_confidence: {artifacts['mean_confidence']:.4f}")
    print(f"- lung_total_area: {artifacts['lung_total_area']:.0f}")
    print(f"- cardiothoracic_ratio: {artifacts['cardiothoracic_ratio']:.4f}")
    for _, class_name in CLASS_ORDER:
        print(
            f"- {class_name}: area={artifacts[f'{class_name}_area']:.0f}, "
            f"ratio={artifacts[f'{class_name}_ratio']:.4f}, "
            f"mean_confidence={artifacts[f'{class_name}_mean_confidence']:.4f}"
        )


def print_supervised_metrics(metrics: dict[str, Any]) -> None:
    print('监督指标:')
    print(f"- pixel_accuracy: {metrics['pixel_accuracy']:.4f}")
    print(f"- mean_dice: {metrics['mean_dice']:.4f}")
    print(f"- mean_iou: {metrics['mean_iou']:.4f}")
    for row in metrics['per_class']:
        print(
            f"- {row['class_name']}: dice={row['dice']:.4f}, iou={row['iou']:.4f}, "
            f"precision={row['precision']:.4f}, recall={row['recall']:.4f}, "
            f"pred_area={row['pred_area']:.0f}, gt_area={row['gt_area']:.0f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description='后端分割 overlay 测试脚本')
    parser.add_argument('--image', type=Path, default=DEFAULT_IMAGE_PATH, help='待测试影像路径')
    parser.add_argument('--model', type=Path, default=DEFAULT_MODEL_PATH, help='模型权重路径')
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT_DIR, help='输出目录')
    parser.add_argument('--gt', type=Path, help='可选真值掩膜路径，用于计算 Dice/IoU')
    args = parser.parse_args()

    seg = load_segmentation_service()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    original_gray = cv2.imread(str(args.image), cv2.IMREAD_GRAYSCALE)
    if original_gray is None:
        raise RuntimeError(f'无法读取测试影像: {args.image}')

    model = seg.load_model(str(args.model))
    tensor = seg.preprocess(str(args.image))

    with torch.no_grad():
        prediction = model(tensor)

    artifacts = seg.build_segmentation_artifacts(prediction, original_gray)

    stem = args.image.stem
    overlay_path = args.output_dir / f'{stem}_overlay.png'
    label_path = args.output_dir / f'{stem}_label.png'
    left_view_path = args.output_dir / f'{stem}_left_lung.png'
    right_view_path = args.output_dir / f'{stem}_right_lung.png'
    heart_view_path = args.output_dir / f'{stem}_heart.png'

    cv2.imwrite(str(overlay_path), artifacts['overlay_image'])
    cv2.imwrite(str(label_path), artifacts['label_image'])
    cv2.imwrite(str(left_view_path), artifacts['left_lung_view_image'])
    cv2.imwrite(str(right_view_path), artifacts['right_lung_view_image'])
    cv2.imwrite(str(heart_view_path), artifacts['heart_view_image'])
    comparison_path = save_comparison(args.output_dir, stem, original_gray, artifacts)

    print(f'输入影像: {args.image}')
    print(f'模型权重: {args.model}')
    print(f'overlay: {overlay_path}')
    print(f'label: {label_path}')
    print(f'comparison: {comparison_path}')
    print(f'left_lung_view: {left_view_path}')
    print(f'right_lung_view: {right_view_path}')
    print(f'heart_view: {heart_view_path}')
    print_pred_metrics(artifacts)

    if args.gt:
        gt_labels = load_ground_truth(args.gt, artifacts['label_map'].shape)
        metrics = compute_supervised_metrics(artifacts['label_map'], gt_labels)
        print_supervised_metrics(metrics)
    else:
        print('监督指标: 未提供 --gt，当前只输出预测统计。')


if __name__ == '__main__':
    main()
