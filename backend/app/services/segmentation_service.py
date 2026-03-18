import asyncio
from pathlib import Path
from typing import Any
import sys
import numpy as np


def _require_cv2() -> Any:
    try:
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("OpenCV 未安装") from exc
    return cv2


def _require_torch() -> Any:
    try:
        import torch  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("PyTorch 未安装") from exc
    return torch


def _load_segmentation_config() -> dict[str, Any]:
    default = {
        "img_width": 256,
        "img_height": 256,
        "class_names": ["background", "right_lung", "left_lung", "heart"],
        "class_color_map": {
            0: (0, 0, 0),
            1: (255, 170, 0),
            2: (0, 191, 255),
            3: (220, 20, 60),
        },
    }
    try:
        from segmentation_modules import config as seg_config
    except Exception:
        repo_root = Path(__file__).resolve().parents[3]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        try:
            from segmentation_modules import config as seg_config
        except Exception:
            return default

    return {
        "img_width": int(getattr(seg_config, "IMG_WIDTH", default["img_width"])),
        "img_height": int(getattr(seg_config, "IMG_HEIGHT", default["img_height"])),
        "class_names": list(getattr(seg_config, "CLASS_NAMES", default["class_names"])),
        "class_color_map": dict(getattr(seg_config, "CLASS_COLOR_MAP", default["class_color_map"])),
    }


def preprocess(xray_original_path: str):
    """灰度化 + CLAHE + Resize -> tensor [1,3,H,W]"""
    cv2 = _require_cv2()
    config = _load_segmentation_config()
    img = cv2.imread(xray_original_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError("影像读取失败")
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    img = clahe.apply(img)
    img = cv2.resize(
        img,
        (config["img_width"], config["img_height"]),
        interpolation=cv2.INTER_AREA,
    )
    img = img.astype(np.float32) / 255.0
    img = np.repeat(img[..., None], 3, axis=2)
    torch = _require_torch()
    tensor = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0)
    return tensor


async def run_inference(model, tensor):
    """Run model inference in thread pool."""
    torch = _require_torch()

    def _infer():
        with torch.no_grad():
            output = model(tensor)
            if isinstance(output, (list, tuple)):
                output = output[0]
            return output

    return await asyncio.to_thread(_infer)


def _decode_prediction(mask_tensor, output_size: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    cv2 = _require_cv2()
    torch = _require_torch()

    if isinstance(mask_tensor, torch.Tensor):
        prediction = mask_tensor.detach().cpu().float()
    else:
        prediction = torch.as_tensor(mask_tensor, dtype=torch.float32)

    if prediction.ndim == 4:
        prediction = prediction[0]

    if prediction.ndim == 2:
        label_map = prediction.numpy().astype(np.uint8)
        confidence_map = np.ones_like(label_map, dtype=np.float32)
    elif prediction.ndim == 3 and prediction.shape[0] >= 4:
        probs = torch.softmax(prediction, dim=0).numpy()
        label_map = np.argmax(probs, axis=0).astype(np.uint8)
        confidence_map = np.max(probs, axis=0).astype(np.float32)
    elif prediction.ndim == 3 and prediction.shape[0] == 3:
        probs = torch.sigmoid(prediction).numpy()
        foreground = np.max(probs, axis=0)
        label_map = np.argmax(probs, axis=0).astype(np.uint8) + 1
        label_map[foreground <= 0.5] = 0
        confidence_map = np.where(label_map == 0, 1.0 - foreground, foreground).astype(np.float32)
    else:
        raise RuntimeError(f"不支持的分割输出维度: {tuple(prediction.shape)}")

    out_w, out_h = output_size
    label_map = cv2.resize(label_map, (out_w, out_h), interpolation=cv2.INTER_NEAREST)
    confidence_map = cv2.resize(confidence_map, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
    return label_map, confidence_map


def _build_visual_artifacts(label_map: np.ndarray, confidence_map: np.ndarray, original_img: np.ndarray) -> dict[str, Any]:
    cv2 = _require_cv2()
    config = _load_segmentation_config()
    class_names = config["class_names"]
    class_color_map = config["class_color_map"]

    overlay = cv2.cvtColor(original_img, cv2.COLOR_GRAY2BGR)
    color_mask = np.zeros_like(overlay)

    total_pixels = float(original_img.shape[0] * original_img.shape[1])
    metrics: dict[str, Any] = {
        "image_total_area": total_pixels,
        "mean_confidence": float(confidence_map.mean()),
        "label_map": label_map,
        "confidence_map": confidence_map,
    }

    for class_id, color in class_color_map.items():
        if class_id == 0:
            continue
        class_mask = label_map == class_id
        color_mask[class_mask] = color

        class_name = class_names[class_id] if class_id < len(class_names) else f"class_{class_id}"
        area = float(class_mask.sum())
        metrics[f"{class_name}_mask"] = class_mask.astype(np.uint8)
        metrics[f"{class_name}_area"] = area
        metrics[f"{class_name}_ratio"] = area / total_pixels if total_pixels > 0 else 0.0
        metrics[f"{class_name}_mean_confidence"] = (
            float(confidence_map[class_mask].mean()) if np.any(class_mask) else 0.0
        )

    mask_region = label_map > 0
    overlay[mask_region] = (
        0.55 * overlay[mask_region].astype(np.float32)
        + 0.45 * color_mask[mask_region].astype(np.float32)
    ).astype(np.uint8)

    metrics["overlay_image"] = overlay
    metrics["label_image"] = color_mask
    metrics["left_lung_view_image"] = cv2.bitwise_and(
        original_img, original_img, mask=metrics["left_lung_mask"]
    )
    metrics["right_lung_view_image"] = cv2.bitwise_and(
        original_img, original_img, mask=metrics["right_lung_mask"]
    )
    metrics["heart_view_image"] = cv2.bitwise_and(
        original_img, original_img, mask=metrics["heart_mask"]
    )

    left_area = float(metrics.get("left_lung_area", 0.0))
    right_area = float(metrics.get("right_lung_area", 0.0))
    heart_area = float(metrics.get("heart_area", 0.0))
    lung_total = left_area + right_area
    metrics["lung_total_area"] = lung_total
    metrics["cardiothoracic_ratio"] = heart_area / lung_total if lung_total > 0 else 0.0
    return metrics


def _overlay_mask_with_confidence(
    original_img: np.ndarray,
    label_map: np.ndarray,
    confidence_map: np.ndarray,
    alpha_min: float = 0.2,
    alpha_max: float = 0.7,
) -> np.ndarray:
    cv2 = _require_cv2()
    config = _load_segmentation_config()
    class_color_map = config["class_color_map"]

    if original_img.ndim == 2:
        original_bgr = cv2.cvtColor(original_img, cv2.COLOR_GRAY2BGR)
    else:
        original_bgr = original_img.copy()

    color_mask = np.zeros_like(original_bgr)
    for class_id, color in class_color_map.items():
        if class_id == 0:
            continue
        color_mask[label_map == class_id] = color

    alpha = np.clip(confidence_map.astype(np.float32), 0.0, 1.0)
    alpha = alpha_min + (alpha_max - alpha_min) * alpha
    alpha[label_map == 0] = 0.0
    alpha_3c = np.repeat(alpha[..., None], 3, axis=2)

    overlay = (
        alpha_3c * color_mask.astype(np.float32)
        + (1.0 - alpha_3c) * original_bgr.astype(np.float32)
    ).astype(np.uint8)
    return overlay


def _render_probability_heatmap(confidence_map: np.ndarray) -> np.ndarray:
    cv2 = _require_cv2()
    prob = np.clip(confidence_map.astype(np.float32), 0.0, 1.0)
    prob_u8 = (prob * 255.0).astype(np.uint8)
    return cv2.applyColorMap(prob_u8, cv2.COLORMAP_VIRIDIS)


def _add_panel_title(image: np.ndarray, title: str) -> np.ndarray:
    cv2 = _require_cv2()
    title_height = 44
    canvas = np.full((image.shape[0] + title_height, image.shape[1], 3), 255, dtype=np.uint8)
    canvas[title_height:] = image
    cv2.putText(
        canvas,
        title,
        (14, 29),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (24, 24, 24),
        2,
        cv2.LINE_AA,
    )
    return canvas


def build_visualization_sample(label_map: np.ndarray, confidence_map: np.ndarray, original_img: np.ndarray) -> np.ndarray:
    cv2 = _require_cv2()
    artifacts = _build_visual_artifacts(label_map, confidence_map, original_img)
    original_bgr = cv2.cvtColor(original_img, cv2.COLOR_GRAY2BGR)
    dynamic_overlay = _overlay_mask_with_confidence(original_img, label_map, confidence_map)
    prob_heatmap = _render_probability_heatmap(confidence_map)

    panels = [
        _add_panel_title(original_bgr, "Original"),
        _add_panel_title(dynamic_overlay, "Overlay"),
        _add_panel_title(artifacts["label_image"], "Pred Mask"),
        _add_panel_title(prob_heatmap, "Max Prob"),
    ]
    return cv2.hconcat(panels)


def build_segmentation_artifacts(mask_tensor, original_img) -> dict[str, Any]:
    h, w = original_img.shape[:2]
    label_map, confidence_map = _decode_prediction(mask_tensor, (w, h))
    artifacts = _build_visual_artifacts(label_map, confidence_map, original_img)
    artifacts["dynamic_overlay_image"] = _overlay_mask_with_confidence(original_img, label_map, confidence_map)
    artifacts["probability_heatmap_image"] = _render_probability_heatmap(confidence_map)
    artifacts["visualization_sample_image"] = build_visualization_sample(label_map, confidence_map, original_img)
    return artifacts


def post_process(mask_tensor, original_img, xray_id: int):
    """Save mask overlay and view images, compute areas."""
    cv2 = _require_cv2()
    artifacts = build_segmentation_artifacts(mask_tensor, original_img)

    from app.utils.file_storage import build_mask_path, build_view_path, build_visualization_path

    mask_path = build_mask_path(xray_id)
    cv2.imwrite(mask_path, artifacts["overlay_image"])
    visualization_path = build_visualization_path(xray_id)
    cv2.imwrite(visualization_path, artifacts["visualization_sample_image"])

    def save_view(view_image, view_name):
        view_path = build_view_path(xray_id, view_name)
        cv2.imwrite(view_path, view_image)
        return view_path

    left_path = save_view(artifacts["left_lung_view_image"], "left_lung")
    right_path = save_view(artifacts["right_lung_view_image"], "right_lung")
    heart_path = save_view(artifacts["heart_view_image"], "heart")

    return {
        "mask_path": mask_path,
        "visualization_path": visualization_path,
        "left_lung_view_path": left_path,
        "right_lung_view_path": right_path,
        "heart_view_path": heart_path,
        "heart_area": artifacts["heart_area"],
        "left_lung_area": artifacts["left_lung_area"],
        "right_lung_area": artifacts["right_lung_area"],
        "heart_ratio": artifacts["heart_ratio"],
        "left_lung_ratio": artifacts["left_lung_ratio"],
        "right_lung_ratio": artifacts["right_lung_ratio"],
        "lung_total_area": artifacts["lung_total_area"],
        "cardiothoracic_ratio": artifacts["cardiothoracic_ratio"],
        "mean_confidence": artifacts["mean_confidence"],
    }


def load_model(model_path: str):
    """Load segmentation model from disk."""
    torch = _require_torch()
    path = Path(model_path)
    if not path.exists():
        raise RuntimeError("模型文件不存在")
    try:
        model = torch.jit.load(str(path))
    except Exception:
        checkpoint = torch.load(str(path), map_location="cpu")
        if isinstance(checkpoint, torch.nn.Module):
            model = checkpoint
        elif isinstance(checkpoint, dict):
            state_dict = (
                checkpoint.get("model_state_dict")
                or checkpoint.get("state_dict")
                or checkpoint.get("model")
            )
            if state_dict is None:
                raise RuntimeError("模型检查点缺少 model_state_dict/state_dict 字段")
            model_type = checkpoint.get("model_type", "unet")
            try:
                from segmentation_modules.unet_model import get_model
            except Exception:
                repo_root = Path(__file__).resolve().parents[3]
                if str(repo_root) not in sys.path:
                    sys.path.insert(0, str(repo_root))
                from segmentation_modules.unet_model import get_model
            model = get_model(model_type)
            model.load_state_dict(state_dict)
        else:
            raise RuntimeError("不支持的模型文件格式")
    model.eval()
    return model
