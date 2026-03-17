"""
数据加载和预处理模块
处理SCR数据集中的JPEG原图和PFS轮廓，生成多分类掩膜
"""

import os
import re
import numpy as np
from PIL import Image, ImageDraw
import torch
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import train_test_split
import torchvision.transforms as transforms
from torchvision.transforms import InterpolationMode
try:
    from .config import *
except ImportError:
    from config import *

PFS_NATIVE_SIZE = 1024  # PFS标注原生坐标空间（JSRT/SCR约为1024）


def parse_pfs_polygons(pfs_path):
    """解析.pfs文件中的闭合轮廓坐标（支持同一标签多个多边形）"""
    if not os.path.exists(pfs_path):
        raise FileNotFoundError(f"未找到PFS标注文件: {pfs_path}")

    with open(pfs_path, 'r', errors='ignore') as f:
        content = f.read()

    blocks = re.split(r"\},\s*\r?\n\r?\n\{", content.strip())
    polygons = {}

    for block in blocks:
        label_match = re.search(r"\[Label=([^\]]+)\]", block)
        if not label_match:
            continue
        label = label_match.group(1).strip().lower()

        # 仅处理闭合轮廓
        if not re.search(r"\[LineMode=ClosedContour\]", block):
            continue

        points = re.findall(r"\{\s*([0-9\.]+),\s*([0-9\.]+)\s*\}", block)
        if not points:
            continue

        poly = [(float(x), float(y)) for x, y in points]
        polygons.setdefault(label, []).append(poly)

    return polygons


def rasterize_multiclass_mask(size_wh, polygons, class_map=CLASS_LABEL_MAP, priority=CLASS_RASTER_PRIORITY):
    """
    将轮廓栅格化为多分类掩膜

    Args:
        size_wh: (width, height)
        polygons: dict[label -> list[(x, y)]]
        class_map: 标签到类别编号的映射
        priority: 栅格化优先级，高优先级覆盖低优先级
    """
    width, height = size_wh
    mask = np.zeros((height, width), dtype=np.uint8)

    for label in priority:
        if label in polygons and label in class_map:
            canvas = Image.new('L', (width, height), 0)
            draw = ImageDraw.Draw(canvas)

            scale_x = width / PFS_NATIVE_SIZE
            scale_y = height / PFS_NATIVE_SIZE

            for poly in polygons[label]:
                scaled_poly = [(x * scale_x, y * scale_y) for x, y in poly]
                draw.polygon(scaled_poly, outline=1, fill=1)

            poly_mask = np.array(canvas, dtype=np.uint8)
            mask[poly_mask > 0] = class_map[label]

    return mask

class SCRDataset(Dataset):
    """SCR数据集类（基于PFS轮廓动态生成多分类掩膜）"""

    def __init__(self, image_paths, points_paths, transform=None, mask_transform=None):
        """
        初始化数据集

        Args:
            image_paths: 图像路径列表
            points_paths: PFS标注路径列表
            transform: 图像变换
            mask_transform: 掩膜变换
        """
        assert len(image_paths) == len(points_paths), "图像与PFS标注数量不匹配"

        self.image_paths = image_paths
        self.points_paths = points_paths
        self.transform = transform
        self.mask_transform = mask_transform

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        image_path = self.image_paths[idx]
        points_path = self.points_paths[idx]

        # 读取图像（保持与标注相同分辨率）
        image = Image.open(image_path).convert('RGB')
        width, height = image.size

        # 解析与栅格化掩膜
        polygons = parse_pfs_polygons(points_path)
        mask_np = rasterize_multiclass_mask((width, height), polygons)
        mask_img = Image.fromarray(mask_np, mode='L')

        # 图像变换
        if self.transform:
            image_tensor = self.transform(image)
        else:
            image_tensor = transforms.ToTensor()(image)
            image_tensor = transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                                std=[0.229, 0.224, 0.225])(image_tensor)

        # 掩膜变换
        if self.mask_transform:
            mask_tensor = self.mask_transform(mask_img)
        else:
            mask_resized = mask_img.resize((IMG_WIDTH, IMG_HEIGHT), resample=Image.NEAREST)
            mask_tensor = torch.from_numpy(np.array(mask_resized, dtype=np.int64))

        return image_tensor, mask_tensor

def get_data_transforms():
    """获取数据变换"""

    # 训练/验证图像变换
    train_image_transform = transforms.Compose([
        transforms.Resize((IMG_HEIGHT, IMG_WIDTH), interpolation=InterpolationMode.BILINEAR),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225])
    ])

    val_image_transform = transforms.Compose([
        transforms.Resize((IMG_HEIGHT, IMG_WIDTH), interpolation=InterpolationMode.BILINEAR),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225])
    ])

    def mask_transform(mask_img):
        resized = mask_img.resize((IMG_WIDTH, IMG_HEIGHT), resample=Image.NEAREST)
        return torch.from_numpy(np.array(resized, dtype=np.int64))

    train_mask_transform = mask_transform
    val_mask_transform = mask_transform

    return train_image_transform, val_image_transform, train_mask_transform, val_mask_transform

def load_data_paths():
    """加载图像和PFS标注路径"""

    image_paths = []
    points_paths = []

    # 获取所有图像文件
    image_files = [
        f for f in os.listdir(IMAGE_DIR)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ]
    image_files.sort()

    for img_file in image_files:
        # 图像路径
        img_path = os.path.join(IMAGE_DIR, img_file)
        image_paths.append(img_path)

        # 对应的PFS路径
        base_name, _ = os.path.splitext(img_file)
        pfs_file = base_name + '.pfs'
        pfs_path = os.path.join(POINTS_DIR, pfs_file)

        if os.path.exists(pfs_path):
            points_paths.append(pfs_path)
        else:
            print(f"警告: 找不到PFS标注文件 {pfs_path}")
            points_paths.append(None)

    # 过滤缺失标注的数据
    valid_image_paths = []
    valid_points_paths = []
    for img_path, pfs_path in zip(image_paths, points_paths):
        if pfs_path is None:
            continue
        valid_image_paths.append(img_path)
        valid_points_paths.append(pfs_path)

    return valid_image_paths, valid_points_paths

def create_data_loaders(batch_size=BATCH_SIZE, mask_dir=None, num_workers=4, pin_memory=True):
    """创建数据加载器"""

    # 加载路径
    image_paths, points_paths = load_data_paths()
    total_samples = len(image_paths)
    print(f"找到 {total_samples} 个图像和对应的PFS标注")

    # 数据分割
    combined = list(zip(image_paths, points_paths))
    train_data, temp_data = train_test_split(
        combined,
        test_size=VALIDATION_SPLIT + TEST_SPLIT,
        random_state=42,
        shuffle=True
    )

    val_data, test_data = train_test_split(
        temp_data,
        test_size=TEST_SPLIT / (VALIDATION_SPLIT + TEST_SPLIT),
        random_state=42,
        shuffle=True
    )

    def unzip(data):
        if not data:
            return [], []
        imgs, pts = zip(*data)
        return list(imgs), list(pts)

    train_imgs, train_pts = unzip(train_data)
    val_imgs, val_pts = unzip(val_data)
    test_imgs, test_pts = unzip(test_data)

    print(f"训练集: {len(train_imgs)}, 验证集: {len(val_imgs)}, 测试集: {len(test_imgs)}")

    # 获取数据变换
    (train_image_transform, val_image_transform,
     train_mask_transform, val_mask_transform) = get_data_transforms()

    # 创建数据集
    train_dataset = SCRDataset(
        train_imgs, train_pts,
        transform=train_image_transform,
        mask_transform=train_mask_transform
    )
    val_dataset = SCRDataset(
        val_imgs, val_pts,
        transform=val_image_transform,
        mask_transform=val_mask_transform
    )
    test_dataset = SCRDataset(
        test_imgs, test_pts,
        transform=val_image_transform,
        mask_transform=val_mask_transform
    )

    # 创建数据加载器
    train_loader = DataLoader(train_dataset, batch_size=batch_size,
                            shuffle=True, num_workers=num_workers, pin_memory=pin_memory)
    val_loader = DataLoader(val_dataset, batch_size=batch_size,
                          shuffle=False, num_workers=num_workers, pin_memory=pin_memory)
    test_loader = DataLoader(test_dataset, batch_size=batch_size,
                            shuffle=False, num_workers=num_workers, pin_memory=pin_memory)

    return train_loader, val_loader, test_loader

def test_data_loading(num_workers=0, pin_memory=False):
    """测试数据加载功能"""
    print("测试数据加载...")

    # 创建数据加载器
    train_loader, val_loader, test_loader = create_data_loaders(batch_size=2, num_workers=num_workers, pin_memory=pin_memory)

    # 测试训练数据
    for batch_idx, (images, masks) in enumerate(train_loader):
        print(f"批次 {batch_idx}:")
        print(f"  图像形状: {images.shape}")
        print(f"  掩膜形状: {masks.shape}")
        print(f"  图像值范围: [{images.min():.3f}, {images.max():.3f}]")
        print(f"  掩膜类别: {torch.unique(masks)}")

        if batch_idx == 0:  # 只测试第一个批次
            break

    print("数据加载测试完成！")

if __name__ == "__main__":
    test_data_loading()
