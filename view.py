import cv2
import numpy as np

# ==============================
# 修改下面这 3 行路径即可
# ==============================
mask_left_path  = "data/mimic-cxr-a/masks/p10/p10000032/s50414267/02aa804e-bde0afdd-112c0b34-7bc16630-4e384014_mask_leftlung.png"
mask_right_path = "data/mimic-cxr-a/masks/p10/p10000032/s50414267/02aa804e-bde0afdd-112c0b34-7bc16630-4e384014_mask_rightlung.png"
mask_heart_path = "data/mimic-cxr-a/masks/p10/p10000032/s50414267/02aa804e-bde0afdd-112c0b34-7bc16630-4e384014_mask_heart.png"

# 输出路径（可选修改）
output_path = "example_mask_background.png"


# ====== 读取掩膜（0/255） ======
mask_left  = cv2.imread(mask_left_path,  cv2.IMREAD_GRAYSCALE)
mask_right = cv2.imread(mask_right_path, cv2.IMREAD_GRAYSCALE)
mask_heart = cv2.imread(mask_heart_path, cv2.IMREAD_GRAYSCALE)

# 检查是否读取成功
if mask_left is None:
    raise FileNotFoundError(f"左肺掩膜读取失败: {mask_left_path}")
if mask_right is None:
    raise FileNotFoundError(f"右肺掩膜读取失败: {mask_right_path}")
if mask_heart is None:
    raise FileNotFoundError(f"心脏掩膜读取失败: {mask_heart_path}")

# ====== 转为 0/1 掩膜 ======
left01  = (mask_left  > 0).astype(np.uint8)
right01 = (mask_right > 0).astype(np.uint8)
heart01 = (mask_heart > 0).astype(np.uint8)

# ====== 计算 union（三者并集） ======
union01 = ((left01 + right01 + heart01) > 0).astype(np.uint8)

# ====== 背景 = 1 - union ======
background01 = 1 - union01
background255 = (background01 * 255).astype(np.uint8)

# ====== 保存 ======
cv2.imwrite(output_path, 255-background255)

print(f"背景掩膜生成完成：{output_path}")
