"""
Multi-label MIMIC-CXR dataset loader.

This module is intentionally separate from dataloader.py so the existing
structured MIMIC-CXR-A loading path remains unchanged.
"""

import os
import random
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.utils.data as data
from PIL import Image
from torch.utils.data import DataLoader, WeightedRandomSampler


DEFAULT_METADATA_COLUMNS = {"filename", "split", "label"}


def _get_cfg_value(cfg: Any, key: str, default: Any = None) -> Any:
    if isinstance(cfg, dict):
        return cfg.get(key, default)
    return getattr(cfg, key, default)


def _normalize_split_name(split: str) -> str:
    split = str(split).lower()
    if split in {"val", "validation"}:
        return "valid"
    return split


def infer_label_columns(df: pd.DataFrame, excluded_columns: Optional[Iterable[str]] = None) -> List[str]:
    excluded = set(DEFAULT_METADATA_COLUMNS)
    if excluded_columns is not None:
        excluded.update(excluded_columns)

    label_columns = []
    for col in df.columns:
        if col in excluded:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            label_columns.append(col)

    if not label_columns:
        raise ValueError("未能从 CSV 自动推断多标签列，请在配置中设置 data.label_columns")
    return label_columns


def build_multilabel_transforms(
    image_size: int = 224,
    resize: int = 256,
    train: bool = False,
    augmentation_enabled: bool = True,
    horizontal_flip: float = 0.0,
    mean: Tuple[float, float, float] = (0.485, 0.456, 0.406),
    std: Tuple[float, float, float] = (0.229, 0.224, 0.225),
):
    try:
        from torchvision import transforms
    except ModuleNotFoundError:
        return SimpleImageTransform(
            image_size=image_size,
            resize=resize,
            train=train,
            augmentation_enabled=augmentation_enabled,
            horizontal_flip=horizontal_flip,
            mean=mean,
            std=std,
        )

    if train and augmentation_enabled:
        return transforms.Compose(
            [
                transforms.Resize((resize, resize)),
                transforms.RandomCrop((image_size, image_size)),
                transforms.RandomHorizontalFlip(p=float(horizontal_flip)),
                transforms.ToTensor(),
                transforms.Normalize(mean, std),
            ]
        )

    return transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.ToTensor(),
            transforms.Normalize(mean, std),
        ]
    )


class SimpleImageTransform:
    """Small PIL/torch fallback used when torchvision is unavailable."""

    def __init__(
        self,
        image_size: int,
        resize: int,
        train: bool,
        augmentation_enabled: bool,
        horizontal_flip: float,
        mean: Tuple[float, float, float],
        std: Tuple[float, float, float],
    ):
        self.image_size = int(image_size)
        self.resize = int(resize)
        self.train = bool(train)
        self.augmentation_enabled = bool(augmentation_enabled)
        self.horizontal_flip = float(horizontal_flip)
        self.mean = torch.tensor(mean, dtype=torch.float32).view(3, 1, 1)
        self.std = torch.tensor(std, dtype=torch.float32).view(3, 1, 1)

    def __call__(self, image: Image.Image) -> torch.Tensor:
        resample = getattr(Image, "Resampling", Image).BILINEAR
        image = image.resize((self.resize, self.resize), resample)

        if self.train and self.augmentation_enabled and self.image_size < self.resize:
            max_offset = self.resize - self.image_size
            left = random.randint(0, max_offset)
            top = random.randint(0, max_offset)
            image = image.crop((left, top, left + self.image_size, top + self.image_size))
        elif self.image_size != self.resize:
            left = max(0, (self.resize - self.image_size) // 2)
            top = max(0, (self.resize - self.image_size) // 2)
            image = image.crop((left, top, left + self.image_size, top + self.image_size))

        if self.train and self.augmentation_enabled and self.horizontal_flip > 0:
            if random.random() < self.horizontal_flip:
                image = image.transpose(Image.FLIP_LEFT_RIGHT)

        array = np.asarray(image, dtype=np.float32).copy() / 255.0
        tensor = torch.from_numpy(array).permute(2, 0, 1).contiguous()
        return (tensor - self.mean) / self.std


class MIMICCXRMultiLabelDataset(data.Dataset):
    """
    Dataset for data/mimic-cxr-multilabels.

    Expected layout:
      root_dir/
        mimic-cxr.csv
        train/*.jpg
        valid/*.jpg
        test/*.jpg

    CSV must contain filename, split and one numeric column per label.
    """

    def __init__(
        self,
        csv_path: str,
        root_dir: str,
        split: str,
        label_columns: Optional[List[str]] = None,
        transform=None,
        skip_missing: bool = True,
    ):
        self.csv_path = csv_path
        self.root_dir = root_dir
        self.split = _normalize_split_name(split)
        self.transform = transform
        self.skip_missing = skip_missing

        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"多标签 CSV 不存在: {csv_path}")
        if not os.path.isdir(root_dir):
            raise FileNotFoundError(f"多标签数据目录不存在: {root_dir}")

        df = pd.read_csv(csv_path)
        if "filename" not in df.columns:
            raise KeyError("CSV 缺少 filename 列")
        if "split" not in df.columns:
            raise KeyError("CSV 缺少 split 列")

        df = df.copy()
        df["split"] = df["split"].map(_normalize_split_name)
        df = df[df["split"] == self.split].reset_index(drop=True)
        if df.empty:
            raise ValueError(f"split={self.split} 没有样本")

        if label_columns is None:
            label_columns = infer_label_columns(df)
        missing_label_cols = [c for c in label_columns if c not in df.columns]
        if missing_label_cols:
            raise KeyError(f"CSV 缺少标签列: {missing_label_cols}")

        self.label_columns = list(label_columns)
        df[self.label_columns] = df[self.label_columns].fillna(0.0).astype("float32")

        if skip_missing:
            exists_mask = df["filename"].map(lambda name: os.path.exists(self._image_path(name)))
            missing_count = int((~exists_mask).sum())
            if missing_count > 0:
                print(f"[{self.split}] 跳过缺失图像: {missing_count}")
            df = df[exists_mask].reset_index(drop=True)
            if df.empty:
                raise RuntimeError(f"split={self.split} 过滤缺失图像后没有可用样本")

        self.data = df
        print(f"MIMIC-CXR multilabel {self.split}: {len(self.data)} samples, {len(self.label_columns)} labels")

    def _image_path(self, filename: str) -> str:
        return os.path.join(self.root_dir, self.split, str(filename))

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, index: int) -> Dict[str, Any]:
        row = self.data.iloc[index]
        image_path = self._image_path(row["filename"])

        try:
            image = Image.open(image_path).convert("RGB")
        except Exception as exc:
            raise RuntimeError(f"无法读取图像 {image_path}: {exc}") from exc

        if self.transform is not None:
            image = self.transform(image)

        labels = torch.tensor(row[self.label_columns].to_numpy(dtype="float32"), dtype=torch.float32)
        return {
            "images": image,
            "labels": labels,
            "image_path": image_path,
            "filename": str(row["filename"]),
        }

    def get_label_names(self) -> List[str]:
        return list(self.label_columns)

    def label_matrix(self) -> torch.Tensor:
        return torch.tensor(self.data[self.label_columns].to_numpy(dtype="float32"), dtype=torch.float32)


def build_multilabel_sample_weights(dataset: MIMICCXRMultiLabelDataset) -> torch.Tensor:
    labels = dataset.label_matrix()
    positives = labels.sum(dim=0)
    negatives = labels.size(0) - positives
    pos_weight = negatives / torch.clamp(positives, min=1.0)
    sample_positive_counts = labels.sum(dim=1)
    weighted_positive_sum = (labels * pos_weight.unsqueeze(0)).sum(dim=1)
    sample_weights = weighted_positive_sum / torch.clamp(sample_positive_counts, min=1.0)

    no_positive = sample_positive_counts == 0
    if no_positive.any():
        sample_weights[no_positive] = 1.0

    sample_weights = torch.nan_to_num(sample_weights, nan=1.0, posinf=1.0, neginf=1.0)
    return torch.clamp(sample_weights, min=1e-3)


def create_mimic_cxr_multilabel_data_loaders(args: Any):
    root_dir = _get_cfg_value(args, "root_dir", "data/mimic-cxr-multilabels")
    csv_path = _get_cfg_value(args, "csv_path", None) or _get_cfg_value(args, "data_path", None)
    if csv_path is None:
        csv_path = os.path.join(root_dir, "mimic-cxr.csv")

    label_columns = _get_cfg_value(args, "label_columns", None)
    if label_columns is not None:
        label_columns = list(label_columns)

    batch_size = int(_get_cfg_value(args, "batch_size", 32))
    num_workers = int(_get_cfg_value(args, "num_workers", 0))
    pin_memory = bool(_get_cfg_value(args, "pin_memory", True))
    drop_last = bool(_get_cfg_value(args, "drop_last", False))
    skip_missing = bool(_get_cfg_value(args, "skip_missing", True))
    sampler_mode = str(_get_cfg_value(args, "sampler", "none")).lower()

    aug = _get_cfg_value(args, "augmentation", {}) or {}
    image_size = int(aug.get("crop_size", aug.get("image_size", 224)))
    resize = int(aug.get("resize", image_size))
    normalize = aug.get("normalize", {}) or {}
    mean = tuple(normalize.get("mean", [0.485, 0.456, 0.406]))
    std = tuple(normalize.get("std", [0.229, 0.224, 0.225]))

    train_transform = build_multilabel_transforms(
        image_size=image_size,
        resize=resize,
        train=True,
        augmentation_enabled=bool(aug.get("enabled", True)),
        horizontal_flip=float(aug.get("random_horizontal_flip", 0.0)),
        mean=mean,
        std=std,
    )
    eval_transform = build_multilabel_transforms(
        image_size=image_size,
        resize=resize,
        train=False,
        augmentation_enabled=False,
        mean=mean,
        std=std,
    )

    train_dataset = MIMICCXRMultiLabelDataset(
        csv_path=csv_path,
        root_dir=root_dir,
        split="train",
        label_columns=label_columns,
        transform=train_transform,
        skip_missing=skip_missing,
    )
    inferred_labels = train_dataset.get_label_names()

    val_dataset = MIMICCXRMultiLabelDataset(
        csv_path=csv_path,
        root_dir=root_dir,
        split="valid",
        label_columns=inferred_labels,
        transform=eval_transform,
        skip_missing=skip_missing,
    )
    test_dataset = MIMICCXRMultiLabelDataset(
        csv_path=csv_path,
        root_dir=root_dir,
        split="test",
        label_columns=inferred_labels,
        transform=eval_transform,
        skip_missing=skip_missing,
    )

    train_sampler = None
    train_shuffle = True
    if sampler_mode in {"weighted", "weighted_random", "balanced"}:
        sample_weights = build_multilabel_sample_weights(train_dataset)
        train_sampler = WeightedRandomSampler(
            weights=sample_weights.double(),
            num_samples=len(sample_weights),
            replacement=True,
        )
        train_shuffle = False
        print(f"[train] 使用 WeightedRandomSampler 处理多标签类别不均衡")

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=train_shuffle,
        sampler=train_sampler,
        num_workers=num_workers,
        pin_memory=pin_memory,
        drop_last=drop_last,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
        drop_last=False,
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
        drop_last=False,
    )

    return train_loader, val_loader, test_loader, inferred_labels
