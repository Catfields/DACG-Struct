"""
预处理脚本：将PFS轮廓批量栅格化为多分类掩膜
"""

import argparse
import os
from pathlib import Path

import numpy as np
from PIL import Image
from tqdm import tqdm

try:
    from .config import (
        CLASS_COLOR_MAP,
        CLASS_NAMES,
        CLASS_RASTER_PRIORITY,
        CLASS_LABEL_MAP,
        IMAGE_DIR,
        POINTS_DIR,
        NUM_CLASSES,
    )
    from .data_loader import parse_pfs_polygons, rasterize_multiclass_mask
except ImportError:
    from config import (
        CLASS_COLOR_MAP,
        CLASS_NAMES,
        CLASS_RASTER_PRIORITY,
        CLASS_LABEL_MAP,
        IMAGE_DIR,
        POINTS_DIR,
        NUM_CLASSES,
    )
    from data_loader import parse_pfs_polygons, rasterize_multiclass_mask


def build_palette():
    """根据配置构建调色板"""
    palette = np.zeros((NUM_CLASSES, 3), dtype=np.uint8)
    for idx in range(NUM_CLASSES):
        default_color = (
            int(255 * idx / max(1, NUM_CLASSES - 1)),
            int(128 * idx / max(1, NUM_CLASSES - 1)),
            int(64 * idx / max(1, NUM_CLASSES - 1)),
        )
        palette[idx] = np.array(CLASS_COLOR_MAP.get(idx, default_color), dtype=np.uint8)
    return palette


def preprocess(output_dir, color_dir=None, overwrite=False):
    """批量生成多分类掩膜"""
    output_dir = Path(output_dir)
    color_dir = Path(color_dir) if color_dir else None

    output_dir.mkdir(parents=True, exist_ok=True)
    if color_dir:
        color_dir.mkdir(parents=True, exist_ok=True)

    image_files = sorted([f for f in os.listdir(IMAGE_DIR) if f.endswith('.jpg')])
    palette = build_palette()

    for filename in tqdm(image_files, desc="生成多分类掩膜"):
        image_path = Path(IMAGE_DIR) / filename
        pfs_path = Path(POINTS_DIR) / (Path(filename).stem + '.pfs')

        if not pfs_path.exists():
            print(f"跳过 {filename}: 未找到 {pfs_path}")
            continue

        output_path = output_dir / (Path(filename).stem + '.png')
        if output_path.exists() and not overwrite:
            continue

        image = Image.open(image_path).convert('RGB')
        polygons = parse_pfs_polygons(str(pfs_path))
        mask_np = rasterize_multiclass_mask(image.size, polygons,
                                            class_map=CLASS_LABEL_MAP,
                                            priority=CLASS_RASTER_PRIORITY)

        mask_img = Image.fromarray(mask_np.astype(np.uint8), mode='L')
        mask_img.save(output_path)

        if color_dir:
            color_mask = palette[mask_np]
            Image.fromarray(color_mask).save(color_dir / (Path(filename).stem + '.png'))


def parse_args():
    parser = argparse.ArgumentParser(description="将PFS轮廓转换为多分类掩膜文件")
    parser.add_argument('--output_dir', type=str, default=str(Path(IMAGE_DIR).parent / 'masks_multiclass'),
                        help='保存标签编号掩膜的目录')
    parser.add_argument('--color_dir', type=str,
                        help='可选的彩色可视化掩膜输出目录')
    parser.add_argument('--overwrite', action='store_true', help='若已存在则覆盖')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    preprocess(args.output_dir, args.color_dir, overwrite=args.overwrite)
