import os
import cv2
import numpy as np

# 根目录
ROOT_DIR = "/home/y530/handsome/DACG/data/mimic-cxr-a"

IMAGES_ROOT = os.path.join(ROOT_DIR, "images")
MASKS_ROOT = os.path.join(ROOT_DIR, "masks")

# 输出目录：按类别分子目录
OUTPUT_ROOT = os.path.join(ROOT_DIR, "rois")
ROI_TYPES = ["leftlung", "rightlung", "heart", "background"]


def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def find_image_for_mask(rel_dir, base_name):
    """
    在 images 下找到与 mask 对应的原图。
    rel_dir: 相对于 MASKS_ROOT 的子目录，比如 'p10/p1000032/s50414267'
    base_name: 掩膜文件前缀，比如 '02aa804e-bde0afdd-112cb034-7bc16630-4e384014'
    """
    img_dir = os.path.join(IMAGES_ROOT, rel_dir)
    if not os.path.isdir(img_dir):
        return None

    # 在该目录下找以 base_name 开头的文件（任意扩展名）
    for fname in os.listdir(img_dir):
        if fname.startswith(base_name):
            return os.path.join(img_dir, fname)

    return None


def load_mask(mask_path, target_shape=None):
    """
    读入单个掩膜，并做成 0/1 的 uint8 矩阵。
    如给定 target_shape，就用最近邻 resize 到该尺寸。
    """
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return None

    if target_shape is not None and mask.shape != target_shape:
        mask = cv2.resize(mask, (target_shape[1], target_shape[0]),
                          interpolation=cv2.INTER_NEAREST)

    mask01 = (mask > 0).astype(np.uint8)  # 0/1
    return mask01


def main():
    # 先创建输出的大目录
    for roi_type in ROI_TYPES:
        ensure_dir(os.path.join(OUTPUT_ROOT, roi_type))

    # 遍历所有 mask 文件
    for dirpath, dirnames, filenames in os.walk(MASKS_ROOT):
        # 相对路径（相对 MASKS_ROOT），用于在 images 和 output 中复用结构
        rel_dir = os.path.relpath(dirpath, MASKS_ROOT)
        if rel_dir == ".":
            rel_dir = ""

        # 先按照 base_name 把多个 mask 归一组
        # key: base_key = os.path.join(rel_dir, base_name)
        # value: {"leftlung": path, "rightlung": path, "heart": path}
        masks_by_base = {}

        for fname in filenames:
            if "_mask_" not in fname:
                continue
            if not fname.lower().endswith(".png"):
                continue

            # 例子： 02aa804e-...-4e384014_mask_leftlung.png
            prefix, rest = fname.split("_mask_", 1)
            organ = rest.split(".")[0]  # leftlung / rightlung / heart

            base_key = os.path.join(rel_dir, prefix)
            full_path = os.path.join(dirpath, fname)

            if base_key not in masks_by_base:
                masks_by_base[base_key] = {}
            masks_by_base[base_key][organ] = full_path

        # 对这一层目录里的每一组（一个 base_name 对应一张原图）
        for base_key, organ_masks in masks_by_base.items():
            rel_dir_for_img = os.path.dirname(base_key)  # 如 'p10/p1000032/s50414267'
            base_name = os.path.basename(base_key)       # 如 '02aa804e-...-4e384014'

            # 找到对应原图
            img_path = find_image_for_mask(rel_dir_for_img, base_name)
            if img_path is None:
                print(f"[WARN] No image found for {base_key}")
                continue

            img = cv2.imread(img_path, cv2.IMREAD_COLOR)
            if img is None:
                print(f"[WARN] Failed to read image: {img_path}")
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape

            # 读取三个器官的掩膜（可能有缺失）
            left_mask = load_mask(organ_masks.get("leftlung"), target_shape=gray.shape) \
                if "leftlung" in organ_masks else np.zeros_like(gray, dtype=np.uint8)
            right_mask = load_mask(organ_masks.get("rightlung"), target_shape=gray.shape) \
                if "rightlung" in organ_masks else np.zeros_like(gray, dtype=np.uint8)
            heart_mask = load_mask(organ_masks.get("heart"), target_shape=gray.shape) \
                if "heart" in organ_masks else np.zeros_like(gray, dtype=np.uint8)

            # 三者 union
            union_mask = np.clip(left_mask + right_mask + heart_mask, 0, 1).astype(np.uint8)
            background_mask = (1 - union_mask).astype(np.uint8)

            # 生成 ROI
            roi_left = (gray * left_mask).astype(np.uint8)
            roi_right = (gray * right_mask).astype(np.uint8)
            roi_heart = (gray * heart_mask).astype(np.uint8)
            roi_background = (gray * background_mask).astype(np.uint8)

            # 输出路径：保持原有相对结构
            for roi_type, roi_img in [
                ("leftlung", roi_left),
                ("rightlung", roi_right),
                ("heart", roi_heart),
                ("background", roi_background),
            ]:
                out_dir = os.path.join(OUTPUT_ROOT, roi_type, rel_dir_for_img)
                ensure_dir(out_dir)
                out_fname = f"{base_name}_{roi_type}.png"
                out_path = os.path.join(out_dir, out_fname)

                cv2.imwrite(out_path, roi_img)

            print(f"[OK] Processed {base_key}")


if __name__ == "__main__":
    main()
