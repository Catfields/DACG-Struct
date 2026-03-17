"""
配置文件
定义U-Net模型和数据集的配置参数
"""

import os

# 数据路径配置
DATA_ROOT = "/home/y530/handsome/DACG/data/SCR"
IMAGE_DIR = os.path.join(DATA_ROOT, "images/images")
MASK_DIR = os.path.join(DATA_ROOT, "masks/masks")
POINTS_DIR = os.path.join(DATA_ROOT, "points/points")

# 模型参数配置
IMG_HEIGHT = 256
IMG_WIDTH = 256
IMG_CHANNELS = 3
NUM_CLASSES = 4  # 多分类分割：背景、右肺、左肺、心脏
CLASS_NAMES = ["background", "right_lung", "left_lung", "heart"]
CLASS_LABEL_MAP = {
    "right lung": 1,
    "left lung": 2,
    "heart": 3,
}
CLASS_RASTER_PRIORITY = ["heart", "left lung", "right lung"]
CLASS_COLOR_MAP = {
    0: (0, 0, 0),        # background
    1: (255, 170, 0),    # right lung
    2: (0, 191, 255),    # left lung
    3: (220, 20, 60),    # heart
}

# 训练参数配置
BATCH_SIZE = 8
EPOCHS = 100
LEARNING_RATE = 1e-4
VALIDATION_SPLIT = 0.2
TEST_SPLIT = 0.1

# 数据增强参数
ROTATION_RANGE = 10
WIDTH_SHIFT_RANGE = 0.1
HEIGHT_SHIFT_RANGE = 0.1
SHEAR_RANGE = 0.1
ZOOM_RANGE = 0.1
HORIZONTAL_FLIP = True
VERTICAL_FLIP = True

# 设备配置
try:
    import torch
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
except Exception:
    DEVICE = "cpu"

# 输出路径配置
MODEL_SAVE_DIR = "/home/y530/handsome/DACG/segmentation_modules/models/unet_model"
RESULTS_DIR = "/home/y530/handsome/DACG/segmentation_modules/results/unet_results"
LOGS_DIR = "/home/y530/handsome/DACG/segmentation_modules/logs/unet_logs"

# 创建输出目录
os.makedirs(MODEL_SAVE_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
