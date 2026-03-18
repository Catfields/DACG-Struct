#!/usr/bin/env python3
import importlib.util
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from PIL import Image


BACKEND_DIR = Path(__file__).resolve().parents[1]
SERVICE_PATH = BACKEND_DIR / "app" / "services" / "segmentation_service.py"
DEFAULT_IMAGE_PATH = BACKEND_DIR / "tests" / "3.png"
DEFAULT_MODEL_PATH = BACKEND_DIR / "ml_models" / "seg_models" / "upp_model.pth"
DEFAULT_OUTPUT_DIR = BACKEND_DIR / "tests" / "output"


def load_segmentation_service():
    spec = importlib.util.spec_from_file_location("segmentation_service_local", SERVICE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_segmentation_config(seg_module) -> dict[str, Any]:
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
        if hasattr(seg_module, "_load_segmentation_config"):
            cfg = seg_module._load_segmentation_config()
            if isinstance(cfg, dict):
                return cfg
    except Exception:
        pass

    return default


def preprocess_like_evaluate(image_path: str, img_width: int, img_height: int) -> torch.Tensor:
    """
    复刻 evaluate.py 中的旧前处理：
    RGB + resize + /255 + ImageNet mean/std
    输出: [1, 3, H, W]
    """
    image = Image.open(image_path).convert("RGB")
    image_resized = image.resize((img_width, img_height), resample=Image.BILINEAR)
    image_array = np.array(image_resized).astype(np.float32) / 255.0
    image_tensor = torch.from_numpy(image_array).permute(2, 0, 1).float()

    mean = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32).view(3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32).view(3, 1, 1)
    image_tensor = (image_tensor - mean) / std
    image_tensor = image_tensor.unsqueeze(0)
    return image_tensor


def format_metric(name: str, value: Any) -> str:
    if isinstance(value, float):
        return f"{name}: {value:.6f}"
    return f"{name}: {value}"


def main() -> None:
    seg = load_segmentation_service()
    config = load_segmentation_config(seg)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    original_gray = cv2.imread(str(DEFAULT_IMAGE_PATH), cv2.IMREAD_GRAYSCALE)
    assert_true(original_gray is not None, f"无法读取测试影像: {DEFAULT_IMAGE_PATH}")

    img_width = int(config["img_width"])
    img_height = int(config["img_height"])
    class_names = list(config.get("class_names", ["background", "right_lung", "left_lung", "heart"]))

    # 只使用 evaluate.py 的旧前处理
    tensor = preprocess_like_evaluate(str(DEFAULT_IMAGE_PATH), img_width, img_height)

    # 加载模型
    model = seg.load_model(str(DEFAULT_MODEL_PATH))
    model.eval()

    # 推理
    with torch.no_grad():
        prediction = model(tensor)
        if isinstance(prediction, (list, tuple)):
            prediction = prediction[0]

    # 后处理与可视化
    artifacts = seg.build_segmentation_artifacts(prediction, original_gray)

    overlay_path = DEFAULT_OUTPUT_DIR / "visualization_validation_overlay.png"
    visualization_path = DEFAULT_OUTPUT_DIR / "visualization_validation_sample.png"
    pred_mask_path = DEFAULT_OUTPUT_DIR / "visualization_validation_pred_mask.png"
    prob_heatmap_path = DEFAULT_OUTPUT_DIR / "visualization_validation_prob_heatmap.png"
    dynamic_overlay_path = DEFAULT_OUTPUT_DIR / "visualization_validation_dynamic_overlay.png"

    cv2.imwrite(str(overlay_path), artifacts["overlay_image"])
    cv2.imwrite(str(visualization_path), artifacts["visualization_sample_image"])
    cv2.imwrite(str(pred_mask_path), artifacts["label_image"])
    cv2.imwrite(str(prob_heatmap_path), artifacts["probability_heatmap_image"])
    cv2.imwrite(str(dynamic_overlay_path), artifacts["dynamic_overlay_image"])

    visualization = cv2.imread(str(visualization_path))
    assert_true(visualization is not None, "可视化样例图片生成失败")

    expected_height = original_gray.shape[0] + 44
    expected_width = original_gray.shape[1] * 4
    assert_true(
        visualization.shape[:2] == (expected_height, expected_width),
        (
            f"可视化样例尺寸不符合预期: got={visualization.shape[:2]}, "
            f"expected={(expected_height, expected_width)}"
        ),
    )

    panel_width = original_gray.shape[1]
    panel_titles = ["Original", "Overlay", "Pred Mask", "Max Prob"]
    for idx, panel_name in enumerate(panel_titles):
        start = idx * panel_width
        end = start + panel_width
        panel = visualization[:, start:end]
        assert_true(panel.size > 0, f"{panel_name} 面板为空")
        assert_true(np.count_nonzero(panel) > 0, f"{panel_name} 面板内容为空白")

    # 控制台输出
    print("影像分割模块测试成功")
    print(f"overlay_image: {overlay_path}")
    print(f"visualization_image: {visualization_path}")
    print(f"pred_mask_image: {pred_mask_path}")
    print(f"probability_heatmap_image: {prob_heatmap_path}")
    print(f"dynamic_overlay_image: {dynamic_overlay_path}")
    print(f"visualization_shape: {visualization.shape}")
    print(format_metric("mean_confidence", artifacts["mean_confidence"]))
    print(format_metric("image_total_area", artifacts["image_total_area"]))

    for class_name in class_names:
        if class_name == "background":
            continue
        area_key = f"{class_name}_area"
        ratio_key = f"{class_name}_ratio"
        conf_key = f"{class_name}_mean_confidence"

        if area_key in artifacts:
            print(format_metric(area_key, float(artifacts[area_key])))
        if ratio_key in artifacts:
            print(format_metric(ratio_key, float(artifacts[ratio_key])))
        if conf_key in artifacts:
            print(format_metric(conf_key, float(artifacts[conf_key])))

    if "lung_total_area" in artifacts:
        print(format_metric("lung_total_area", float(artifacts["lung_total_area"])))
    if "cardiothoracic_ratio" in artifacts:
        print(format_metric("cardiothoracic_ratio", float(artifacts["cardiothoracic_ratio"])))


if __name__ == "__main__":
    main()