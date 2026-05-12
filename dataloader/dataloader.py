"""
MIMIC-CXR-A 数据集加载器（整理优化版）
- 以 construct_labels() 作为唯一监督口径（multi-head labels + masks）
- Dataset 只负责：读取图像/结构化标注/掩膜，并做 split/mask 过滤
- Collator 负责：组 batch + 调用 construct_labels() 并输出更可读的 dict labels

你需要提供（来自 json 文件）：
- severity_to_id: Dict[str,int]
- disease_modifier_to_id: Dict[str, Dict[str,int]]
- disease_anatomy_to_id: Dict[str, Dict[str,int]]
"""

import os
import json
import ast
import glob
import warnings
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Any, Union

import torch
import torch.utils.data as data
import pandas as pd
from PIL import Image

IGNORE_INDEX = -100


# -----------------------------
# Multi-head labels constructor
# -----------------------------
def construct_labels(
    batch_labels: List[Dict],
    disease_order: List[str],
    severity_to_id: Dict[str, int],
    disease_modifier_to_id: Dict[str, Dict[str, int]],
    disease_anatomy_to_id: Dict[str, Dict[str, int]],
    device: Optional[torch.device] = None,
) -> Dict[str, torch.Tensor]:
    """
    输出更可读的 dict 版本，便于训练代码使用。

    适配 MultiHeadClassifier 输出：
    - mention: float (B,K) 0/1
    - polarity: float (B,K) 0/1  (sigmoid + BCE)
    - probability: long (B,K) 0..2 (3-class) + mask_prob 控制是否监督
    - severity: long (B,K) 0..S-1 + mask_sev
    - modifier/anatomy: long (B,K) + mask_mod/mask_anat
    """
    if device is None:
        device = torch.device("cpu")

    disease_to_idx = {d: i for i, d in enumerate(disease_order)}
    B = len(batch_labels)
    K = len(disease_order)

    mention_labels = torch.zeros(B, K, dtype=torch.float32, device=device)
    polarity_labels = torch.zeros(B, K, dtype=torch.float32, device=device)

    prob_labels = torch.zeros(B, K, dtype=torch.long, device=device)
    sev_labels = torch.zeros(B, K, dtype=torch.long, device=device)

    modifier_labels = torch.full((B, K), IGNORE_INDEX, dtype=torch.long, device=device)
    anatomy_labels = torch.full((B, K), IGNORE_INDEX, dtype=torch.long, device=device)

    mask_pol = torch.zeros(B, K, dtype=torch.bool, device=device)
    mask_prob = torch.zeros(B, K, dtype=torch.bool, device=device)
    mask_sev = torch.zeros(B, K, dtype=torch.bool, device=device)
    mask_mod = torch.zeros(B, K, dtype=torch.bool, device=device)
    mask_anat = torch.zeros(B, K, dtype=torch.bool, device=device)

    for b, label_dict in enumerate(batch_labels):
        pos = label_dict.get("positive_findings", []) or []
        neg = label_dict.get("negative_findings", []) or []

        # positive findings (list[dict])
        for finding in pos:
            if not isinstance(finding, dict):
                continue
            disease_name = finding.get("disease_name") or finding.get("disease")
            if not disease_name or disease_name not in disease_to_idx:
                continue
            k = disease_to_idx[disease_name]

            mention_labels[b, k] = 1.0

            # polarity: positive => 1
            polarity_labels[b, k] = 1.0
            mask_pol[b, k] = True

            # probability:
            # 你的原实现假设 finding["probability"] in {1,2,3} -> 映射到 0..2
            # 这里保留同样逻辑：如果给到 1..3 则 -1；如果给到 0..2 则直接用；
            # 若是 1..4，则先 clamp 到 1..3（你可以按真实数据再调整）
            if "probability" in finding and finding["probability"] is not None:
                try:
                    p = int(finding["probability"])
                    if p in (0, 1, 2):
                        prob_level = p
                    else:
                        # 兼容 1..4：先压到 1..3，再 -1
                        p = max(1, min(3, p))
                        prob_level = p - 1
                    prob_labels[b, k] = prob_level
                    mask_prob[b, k] = True
                except Exception:
                    pass

            # severity: 直接使用 int 值 (0-3) 作为 id，因为：
            # - 数据中 severity 是 int: 0, 1, 2, 3
            # - severity_to_id 的 value 也是 0, 1, 2, 3 (字符串 key 只是为了兼容 "Mild" 等)
            # - 所以直接用 int(severity) 作为标签 id
            severity = finding.get("severity")
            if severity is not None:
                try:
                    sev_id = int(severity)
                    # 验证范围 [0, 3]，超出范围则设为 0 (None/unknown)
                    if 0 <= sev_id <= 3:
                        sev_labels[b, k] = sev_id
                        mask_sev[b, k] = True
                except (ValueError, TypeError):
                    # 如果是字符串 "Mild" 等，走原有字符串映射逻辑
                    sev_key = str(severity)
                    if sev_key in severity_to_id:
                        sev_labels[b, k] = int(severity_to_id[sev_key])
                        mask_sev[b, k] = True

            # location supervision -> modifier/anatomy
            has_loc_supervision = bool(finding.get("has_location_supervision", False))
            if has_loc_supervision:
                loc_mods = finding.get("location_modifiers", []) or []
                if len(loc_mods) > 0:
                    mod_str = str(loc_mods[0])
                    mod_map = disease_modifier_to_id.get(disease_name, {})
                    if mod_str in mod_map:
                        modifier_labels[b, k] = int(mod_map[mod_str])
                        mask_mod[b, k] = True

                loc_concepts = finding.get("location_concepts", []) or []
                if len(loc_concepts) > 0:
                    anat_str = str(loc_concepts[0])
                    anat_map = disease_anatomy_to_id.get(disease_name, {})
                    if anat_str in anat_map:
                        anatomy_labels[b, k] = int(anat_map[anat_str])
                        mask_anat[b, k] = True

    # NOTE: negative findings are NO LONGER used for supervision (point 4).
    # The model uses positive/unknown labeling only. Diseases not in positive_findings
    # are treated as unknown/missing (masked), not as negative.
    # missing labels are already masked by the zero-initialized masks above.

    return {
        "mention_labels": mention_labels,
        "polarity_labels": polarity_labels,
        "prob_labels": prob_labels,
        "sev_labels": sev_labels,
        "modifier_labels": modifier_labels,
        "anatomy_labels": anatomy_labels,
        "mask_pol": mask_pol,
        "mask_prob": mask_prob,
        "mask_sev": mask_sev,
        "mask_mod": mask_mod,
        "mask_anat": mask_anat,
    }


# -----------------------------
# Dataset
# -----------------------------
class MIMICCXRADataset(data.Dataset):
    """
    MIMIC-CXR-A 数据集加载器（整理版）

    - 输出：image_tensor, label_dict(只含 positive/negative_findings + metadata), image_id, mask_tensor(optional)
    - 不再输出第二套 disease_labels/disease_details/probability_scores...（避免冗余）
    """

    def __init__(
        self,
        data_path: str,
        split: str,
        image_dir: str,
        split_dir: Optional[str] = None,
        mask_dir: Optional[str] = None,
        transform=None,
        disease_list: Optional[List[str]] = None,
        load_masks: bool = True,
        data_format: str = "auto",
        require_masks: bool = False,
        no_finding_downsample_ratio: Optional[float] = None,
    ):
        self.data_path = data_path
        self.split = split
        self.image_dir = image_dir
        self.split_dir = split_dir
        self.mask_dir = mask_dir
        self.transform = transform
        self.load_masks = bool(load_masks and mask_dir is not None)
        self.require_masks = bool(require_masks and self.load_masks)
        self.no_finding_downsample_ratio = no_finding_downsample_ratio

        self.mask_index: Dict[str, List[str]] = {}

        # auto detect format
        if data_format == "auto":
            if data_path.endswith(".jsonl"):
                self.data_format = "jsonl"
            elif data_path.endswith(".csv"):
                self.data_format = "csv"
            else:
                raise ValueError(f"无法自动检测数据格式: {data_path}，请指定 data_format")
        else:
            if data_format not in ("jsonl", "csv"):
                raise ValueError(f"不支持 data_format={data_format}")
            self.data_format = data_format

        # default transform (避免 _load_image 重复写三遍)
        if self.transform is None:
            from torchvision import transforms
            self.default_transform = transforms.Compose(
                [
                    transforms.Resize((256, 256)),
                    transforms.ToTensor(),
                    transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
                ]
            )
        else:
            self.default_transform = None

        # load data
        if self.data_format == "jsonl":
            self.data = self._load_jsonl_data()
        else:
            self.data = self._load_csv_data()

        # apply split filtering
        self.split_indices = None
        if split_dir is not None:
            if self.data_format == "jsonl":
                split_ids = self._load_split_image_ids(split_dir, split)
                self.data = [s for s in self.data if self._get_base_id(s) in split_ids]
                print(f"[{split}] jsonl split filter -> {len(self.data)} samples")
            else:
                self.split_indices = self._load_split_indices(split_dir, split)
                self.data = [self.data[i] for i in self.split_indices]
                print(f"[{split}] csv indices filter -> {len(self.data)} samples")

        # mask index + filter invalid
        if self.load_masks:
            self.mask_index = self._build_mask_index()
        self._filter_invalid_samples()

        # ---- no_finding downsampling (point 2) ----
        # Samples where positive_findings is empty and only "no_finding" is listed
        # are downsampled to `no_finding_ratio` (default 0.20 = keep 20%).
        # This is applied after split filtering but before disease vocab building.
        if getattr(self, "no_finding_downsample_ratio", None) is not None:
            ratio = self.no_finding_downsample_ratio
            no_finding_samples = []
            other_samples = []
            for s in self.data:
                pos = s.get("positive_findings", []) or []
                neg = s.get("negative_findings", []) or []
                is_no_finding = (
                    len(pos) == 0 and len(neg) == 1 and neg[0] == "no_finding"
                ) or (
                    len(pos) == 0 and "no_finding" in neg
                )
                if is_no_finding:
                    no_finding_samples.append(s)
                else:
                    other_samples.append(s)

            import random
            keep_count = int(len(no_finding_samples) * ratio)
            random.seed(42)  # reproducible
            kept = random.sample(no_finding_samples, keep_count) if keep_count < len(no_finding_samples) else no_finding_samples
            self.data = other_samples + kept
            print(f"[{self.split}] no_finding downsampled: {len(no_finding_samples)} -> {len(kept)} (ratio={ratio:.2f})")

        # disease vocab
        if disease_list is not None:
            self.disease_list = disease_list
        else:
            self.disease_list = self._build_disease_vocab()

        self.disease_to_id = {d: i for i, d in enumerate(self.disease_list)}

        print(f"MIMIC-CXR-A {split}: {len(self.data)} samples")
        print(f"疾病词汇表大小: {len(self.disease_list)}")
        print(f"掩膜加载: {'启用' if self.load_masks else '禁用'} (require_masks={self.require_masks})")

    # ----- helpers: base id -----
    def _get_base_id(self, sample: Dict) -> str:
        """
        统一的 base_id/uuid 提取逻辑：
        - metadata['id'] 若是 "patient_uuid_findings" -> 取 uuid 部分
        - 否则 fallback 到 image filename stem
        """
        img_id = sample.get("metadata", {}).get("id", "") or ""
        parts = img_id.split("_")
        if len(parts) >= 3:
            return parts[1]

        image_paths = sample.get("metadata", {}).get("image_path", []) or []
        if image_paths:
            filename = os.path.splitext(os.path.basename(image_paths[0]))[0]
            return filename
        return img_id

    # ----- load data -----
    def _load_jsonl_data(self) -> List[Dict]:
        print(f"正在加载 JSONL: {self.data_path}")
        data_list: List[Dict] = []
        with open(self.data_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    warnings.warn(f"第{line_num}行 JSON解析错误: {e}")
                    continue

                metadata = record.get("metadata", {}) or {}
                image_id = metadata.get("id", "")
                image_paths = metadata.get("image_path", []) or []

                # IMPORTANT：为了 construct_labels，这里保留 finding 原始结构（尽量不改字段）
                positive_findings = []
                for finding in record.get("positive_findings", []) or []:
                    if isinstance(finding, dict):
                        # 保证 disease_name 字段存在（兼容某些数据用 disease）
                        if "disease_name" not in finding and "disease" in finding:
                            finding = dict(finding)
                            finding["disease_name"] = finding.get("disease")
                        positive_findings.append(finding)

                full_image_paths = [os.path.join(self.image_dir, p) for p in image_paths]

                sample = {
                    "positive_findings": positive_findings,
                    "negative_findings": record.get("negative_findings", []) or [],
                    "metadata": {
                        "id": image_id,
                        "subject_id": metadata.get("subject_id", ""),
                        "image_path": full_image_paths,
                        "report_type": metadata.get("report_type", "jsonl"),
                        "dataset_type": metadata.get("dataset_type", self.split),
                        "original_report": metadata.get("original_report", ""),
                        "view_type": metadata.get("view_type", ""),
                        "processed_time": metadata.get("processed_time", ""),
                        "worker_id": metadata.get("worker_id", ""),
                    },
                }
                data_list.append(sample)

        print(f"成功加载 {len(data_list)} 条 JSONL 记录")
        return data_list

    def _load_csv_data(self) -> List[Dict]:
        print(f"正在加载 CSV: {self.data_path}")
        df = pd.read_csv(self.data_path)
        print(f"成功加载 {len(df)} 条记录")

        def parse_list_field(x):
            try:
                if pd.isna(x) or x == "[]":
                    return []
                v = ast.literal_eval(x)
                return v if isinstance(v, list) else []
            except Exception:
                return []

        # 兼容你原字段名
        if "positive_diseases_detail" not in df.columns:
            raise KeyError("CSV 缺少列 positive_diseases_detail")
        if "negative_diseases" not in df.columns:
            raise KeyError("CSV 缺少列 negative_diseases")

        df["parsed_positive"] = df["positive_diseases_detail"].apply(parse_list_field)
        df["parsed_negative"] = df["negative_diseases"].apply(parse_list_field)

        data_list: List[Dict] = []
        for _, row in df.iterrows():
            pos_raw = row["parsed_positive"]
            pos_findings: List[Dict] = []
            for item in pos_raw:
                if not isinstance(item, dict):
                    continue
                # 兼容 disease_name / disease
                dname = item.get("disease_name") or item.get("disease")
                if not dname:
                    continue
                # 保留原始字段（尤其是 location_modifiers/location_concepts/has_location_supervision）
                finding = dict(item)
                finding["disease_name"] = dname
                pos_findings.append(finding)

            image_path = row.get("image_path", "")
            full_image_path = os.path.join(self.image_dir, str(image_path))

            sample = {
                "positive_findings": pos_findings,
                "negative_findings": row["parsed_negative"],
                "metadata": {
                    "id": str(row.get("image_id", "")),
                    "subject_id": str(row.get("subject_id", "")),
                    "image_path": [full_image_path],
                    "report_type": "structured_csv",
                    "dataset_type": self.split,
                    "original_findings": str(row.get("findings", "")),
                    "original_impressions": str(row.get("impressions", "")),
                    "view_type": str(row.get("view_type", "")),
                    "full_report": str(row.get("full_report", "")),
                    # processed_time 不建议每次 now（可复现性差），这里用空字符串
                    "processed_time": "",
                    "worker_id": "mimic_cxr_a_dataloader_refactor",
                },
            }
            data_list.append(sample)

        print("CSV 数据解析完成")
        return data_list

    # ----- split loading -----
    def _load_split_image_ids(self, split_dir: str, split: str) -> set:
        split_file = os.path.join(split_dir, f"{split}_image_ids.txt")
        if not os.path.exists(split_file):
            raise FileNotFoundError(f"分割文件不存在: {split_file}")

        image_ids = set()
        with open(split_file, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    image_ids.add(line)
        print(f"加载分割文件: {split}_image_ids.txt -> {len(image_ids)} ids")
        return image_ids

    def _load_split_indices(self, split_dir: str, split: str) -> List[int]:
        split_file = os.path.join(split_dir, f"{split}_indices.json")
        if not os.path.exists(split_file):
            raise FileNotFoundError(f"分割索引文件不存在: {split_file}")
        with open(split_file, "r") as f:
            indices = json.load(f)
        if not isinstance(indices, list):
            raise ValueError(f"{split_file} 不是 list")
        return [int(i) for i in indices]

    # ----- disease vocab -----
    def _build_disease_vocab(self) -> List[str]:
        disease_set = set()
        for sample in self.data:
            for finding in sample.get("positive_findings", []) or []:
                if isinstance(finding, dict):
                    dn = finding.get("disease_name") or finding.get("disease")
                    if dn:
                        disease_set.add(dn)
            for dn in sample.get("negative_findings", []) or []:
                if dn:
                    disease_set.add(dn)
        return sorted(disease_set)

    # ----- masks -----
    def _build_mask_index(self) -> Dict[str, List[str]]:
        if not os.path.isdir(self.mask_dir):
            raise FileNotFoundError(f"掩膜目录不存在: {self.mask_dir}")

        mask_index: Dict[str, List[str]] = defaultdict(list)
        pattern = os.path.join(self.mask_dir, "**", "*.png")
        for mask_path in glob.glob(pattern, recursive=True):
            filename = os.path.splitext(os.path.basename(mask_path))[0]
            # e.g. 02aa..._mask_heart
            if "_mask_" in filename:
                uuid_part, _ = filename.split("_mask_", 1)
            else:
                uuid_part = filename
            mask_index[uuid_part].append(mask_path)

        if not mask_index:
            raise RuntimeError(f"在掩膜目录 {self.mask_dir} 下未找到任何 PNG 掩膜文件")
        return dict(mask_index)

    def _infer_organ_from_filename(self, filename: str) -> Optional[str]:
        name = filename.lower()
        if "left" in name and ("lung" in name or "pulmonary" in name):
            return "left_lung"
        if "right" in name and ("lung" in name or "pulmonary" in name):
            return "right_lung"
        if "heart" in name or "cardiac" in name:
            return "heart"
        return None

    def _select_mask_paths(self, base_id: str) -> Optional[Dict[str, str]]:
        candidates = self.mask_index.get(base_id, [])
        if not candidates:
            return None

        organ_to_path: Dict[str, str] = {}
        for p in candidates:
            organ = self._infer_organ_from_filename(os.path.basename(p))
            if organ is not None and organ not in organ_to_path:
                organ_to_path[organ] = p

        required = ["left_lung", "right_lung", "heart"]
        if all(k in organ_to_path for k in required):
            return {k: organ_to_path[k] for k in required}
        return None

    def _filter_invalid_samples(self) -> None:
        filtered = []
        missing_images, missing_masks = [], []

        for sample in self.data:
            image_paths = sample.get("metadata", {}).get("image_path", []) or []
            if not image_paths:
                missing_images.append("(empty image_path)")
                continue
            image_path = image_paths[0]
            if not os.path.exists(image_path):
                missing_images.append(image_path)
                continue

            if self.load_masks:
                base_id = self._get_base_id(sample)
                mask_paths = self._select_mask_paths(base_id)
                if mask_paths is None:
                    missing_masks.append(base_id)
                    if self.require_masks:
                        continue
                else:
                    sample["metadata"]["mask_paths"] = mask_paths

            filtered.append(sample)

        if not filtered:
            msg = "过滤后没有可用样本。"
            if missing_images:
                msg += f" 缺失图像数量: {len(missing_images)} 示例: {missing_images[:3]};"
            if self.load_masks and missing_masks:
                msg += f" 缺失掩膜数量: {len(missing_masks)} 示例 base_id: {missing_masks[:3]};"
            raise RuntimeError(msg)

        if missing_images:
            warnings.warn(f"{len(missing_images)} 个样本因图像缺失被跳过，示例: {missing_images[:3]}")
        if self.load_masks and missing_masks and self.require_masks:
            warnings.warn(f"{len(missing_masks)} 个样本因掩膜缺失被跳过（require_masks=True），示例: {missing_masks[:3]}")
        elif self.load_masks and missing_masks:
            warnings.warn(f"{len(missing_masks)} 个样本缺失掩膜（require_masks=False，将返回 mask=None），示例: {missing_masks[:3]}")

        self.data = filtered

    def _get_image_target_size(self) -> Tuple[int, int]:
        """
        给 mask resize 用的目标尺寸。为了避免和 image 不一致：
        - 若使用自定义 transform，尽力从 transform 推断 size
        - 否则与默认 transform 对齐 (256,256)
        """
        if self.transform is None:
            return (256, 256)

        if hasattr(self.transform, "transforms"):
            for t in getattr(self.transform, "transforms", []):
                if hasattr(t, "size"):
                    size = t.size
                    if isinstance(size, (tuple, list)):
                        # torchvision 有时给 (H,W) 或 (shorter_edge,)
                        if len(size) >= 2:
                            return (int(size[-2]), int(size[-1]))
                        if len(size) == 1:
                            s = int(size[0])
                            return (s, s)
                    else:
                        s = int(size)
                        return (s, s)

        # fallback：常见 crop 224
        return (224, 224)

    def _load_image(self, sample: Dict) -> torch.Tensor:
        image_path = (sample.get("metadata", {}).get("image_path", []) or [""])[0]
        transform = self.transform or self.default_transform

        if not os.path.exists(image_path):
            warnings.warn(f"图像文件不存在: {image_path} -> 使用 dummy")
            dummy = Image.new("RGB", (256, 256), (0, 0, 0))
            return transform(dummy)

        try:
            img = Image.open(image_path).convert("RGB")
        except Exception as e:
            warnings.warn(f"无法加载图像 {image_path}: {e} -> 使用 dummy")
            img = Image.new("RGB", (256, 256), (0, 0, 0))

        return transform(img)

    def _load_mask_image(self, sample: Dict) -> Optional[torch.Tensor]:
        """
        加载三张单通道器官掩膜并拼成 (3,H,W)：[左肺, 右肺, 心脏]
        关键优化：
        - 过滤阶段已写入 metadata['mask_paths']，这里不再重复查找（避免冗余 + 避免 base_id bug）
        """
        mask_paths = sample.get("metadata", {}).get("mask_paths", None)
        if mask_paths is None:
            return None

        target_size = self._get_image_target_size()
        from torchvision import transforms
        mask_transform = transforms.Compose(
            [
                transforms.Resize(target_size),
                transforms.ToTensor(),  # (1,H,W) in [0,1]
            ]
        )

        try:
            masks = []
            for key in ["left_lung", "right_lung", "heart"]:
                p = mask_paths.get(key, "")
                if not p or not os.path.exists(p):
                    warnings.warn(f"掩膜文件不存在或缺失: {key} -> {p}")
                    return None
                m = Image.open(p).convert("L")
                m = mask_transform(m)       # (1,H,W)
                m = (m > 0.5).float()       # binarize
                masks.append(m.squeeze(0))  # (H,W)

            return torch.stack(masks, dim=0)  # (3,H,W)
        except Exception as e:
            warnings.warn(f"加载三通道掩膜失败: {e}")
            return None

    # ----- dataset protocol -----
    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, index: int):
        sample = self.data[index]
        image = self._load_image(sample)

        mask_image = None
        if self.load_masks:
            mask_image = self._load_mask_image(sample)

        targets = {
            "positive_findings": sample.get("positive_findings", []) or [],
            "negative_findings": sample.get("negative_findings", []) or [],
            "metadata": sample.get("metadata", {}) or {},
        }

        return image, targets, sample["metadata"]["id"], mask_image

    # ----- info -----
    def get_disease_list(self) -> List[str]:
        return self.disease_list.copy()

    def get_split_info(self) -> Dict[str, Any]:
        return {
            "split": self.split,
            "sample_count": len(self.data),
            "disease_count": len(self.disease_list),
            "data_path": self.data_path,
            "has_split_indices": self.split_indices is not None,
            "load_masks": self.load_masks,
            "require_masks": self.require_masks,
        }


# -----------------------------
# Collator
# -----------------------------
class MIMICCXRACollator:
    """
    - stack images / masks
    - 调用 construct_labels() 并输出更可读 dict labels
    """

    def __init__(
        self,
        disease_order: List[str],
        severity_to_id: Dict[str, int],
        disease_modifier_to_id: Dict[str, Dict[str, int]],
        disease_anatomy_to_id: Dict[str, Dict[str, int]],
        device: Optional[torch.device] = None,
    ):
        self.disease_order = disease_order
        self.severity_to_id = severity_to_id
        self.disease_modifier_to_id = disease_modifier_to_id
        self.disease_anatomy_to_id = disease_anatomy_to_id
        self.device = device

    def __call__(self, batch: List[Tuple]) -> Dict[str, Any]:
        images, targets_list, image_ids, mask_images = [], [], [], []

        for img, t, img_id, m in batch:
            images.append(img)
            targets_list.append(t)
            image_ids.append(img_id)
            mask_images.append(m)

        batch_images = torch.stack(images, dim=0)

        # mask: 如果 batch 内存在 None，则统一返回 None（更明确）
        batch_mask_images = None
        if all(m is not None for m in mask_images):
            batch_mask_images = torch.stack(mask_images, dim=0)

        label_dicts = [
            {
                "positive_findings": t.get("positive_findings", []) or [],
                "negative_findings": t.get("negative_findings", []) or [],
            }
            for t in targets_list
        ]

        labels = construct_labels(
            batch_labels=label_dicts,
            disease_order=self.disease_order,
            severity_to_id=self.severity_to_id,
            disease_modifier_to_id=self.disease_modifier_to_id,
            disease_anatomy_to_id=self.disease_anatomy_to_id,
            device=self.device or batch_images.device,
        )

        return {
            "images": batch_images,
            "labels": labels,  # dict of tensors
            "targets": labels,  # 向后兼容旧训练器命名
            "batch_labels": label_dicts,  # 原始标签，供 S-Score/调试使用
            "image_ids": image_ids,
            "mask_images": batch_mask_images,
            "metadata": [t.get("metadata", {}) for t in targets_list],
        }


# -----------------------------
# Utilities: load label maps
# -----------------------------
def _load_json(path: str) -> Any:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_label_maps(
    severity_to_id_json: Optional[str],
    disease_modifier_to_id_json: Optional[str],
    disease_anatomy_to_id_json: Optional[str],
) -> Tuple[Dict[str, int], Dict[str, Dict[str, int]], Dict[str, Dict[str, int]]]:
    if not severity_to_id_json or not disease_modifier_to_id_json or not disease_anatomy_to_id_json:
        raise ValueError("load_label_maps 需要提供三个 json 路径")

    severity_to_id = _load_json(severity_to_id_json)
    disease_modifier_to_id = _load_json(disease_modifier_to_id_json)
    disease_anatomy_to_id = _load_json(disease_anatomy_to_id_json)

    if not isinstance(severity_to_id, dict):
        raise ValueError("severity_to_id json 必须是 dict")
    if not isinstance(disease_modifier_to_id, dict):
        raise ValueError("disease_modifier_to_id json 必须是 dict")
    if not isinstance(disease_anatomy_to_id, dict):
        raise ValueError("disease_anatomy_to_id json 必须是 dict")

    # 保证内部的 id 是 int（有些 json 会把数字读成 int，但也可能是 str）
    severity_to_id = {str(k): int(v) for k, v in severity_to_id.items()}
    disease_modifier_to_id = {
        str(d): {str(k): int(v) for k, v in m.items()} for d, m in disease_modifier_to_id.items()
    }
    disease_anatomy_to_id = {
        str(d): {str(k): int(v) for k, v in m.items()} for d, m in disease_anatomy_to_id.items()
    }

    return severity_to_id, disease_modifier_to_id, disease_anatomy_to_id


def build_label_maps_from_candidates(
    split_dir: str,
    disease_list: Optional[List[str]] = None,
) -> Tuple[Dict[str, int], Dict[str, Dict[str, int]], Dict[str, Dict[str, int]]]:
    """
    当没有预生成 maps/*.json 时，基于 disease_location_candidates.json 动态构建。
    """
    candidates_path = os.path.join(split_dir, "disease_location_candidates.json")
    if not os.path.exists(candidates_path):
        raise FileNotFoundError(
            f"未找到标签映射文件，且无法动态构建：{candidates_path}"
        )

    with open(candidates_path, "r", encoding="utf-8") as f:
        candidates = json.load(f)

    if disease_list is None:
        disease_list = list(candidates.keys())

    severity_to_id = {
        "None": 0, "none": 0, "": 0,
        "Mild": 1, "mild": 1,
        "Moderate": 2, "moderate": 2,
        "Severe": 3, "severe": 3,
    }

    disease_modifier_to_id: Dict[str, Dict[str, int]] = {}
    disease_anatomy_to_id: Dict[str, Dict[str, int]] = {}
    for disease in disease_list:
        info = candidates.get(disease, {})
        modifier_candidates = info.get("modifier_candidates", []) or []
        anatomy_candidates = info.get("concept_candidates", []) or []

        disease_modifier_to_id[disease] = {
            str(name): idx for idx, name in enumerate(modifier_candidates)
        }
        disease_anatomy_to_id[disease] = {
            str(name): idx for idx, name in enumerate(anatomy_candidates)
        }

    return severity_to_id, disease_modifier_to_id, disease_anatomy_to_id


# -----------------------------
# Create data loaders
# -----------------------------
def create_mimic_cxr_data_loaders(
    args,
    split_dir: str,
    severity_to_id_json: Optional[str] = None,
    disease_modifier_to_id_json: Optional[str] = None,
    disease_anatomy_to_id_json: Optional[str] = None,
    disease_list: Optional[List[str]] = None,
    transform_train=None,
    transform_val=None,
    load_masks: bool = True,
    require_masks: bool = False,
    data_format: str = "auto",
    device: Optional[torch.device] = None,
    no_finding_downsample_ratio: Optional[float] = None,
):
    """
    args 需要至少包含：
    - data_path 或 csv_path
    - image_dir
    - mask_dir（如果 load_masks=True）
    - batch_size
    - num_workers（可选）
    - no_finding_downsample_ratio（可选，用于下采样 no_finding 样本）
    """
    # transforms
    if transform_train is None:
        from torchvision import transforms
        transform_train = transforms.Compose(
            [
                transforms.Resize(256),
                transforms.RandomCrop(224),
                transforms.RandomHorizontalFlip(),
                transforms.ToTensor(),
                transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
            ]
        )

    if transform_val is None:
        from torchvision import transforms
        transform_val = transforms.Compose(
            [
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
            ]
        )

    data_path = getattr(args, "data_path", None) or getattr(args, "csv_path", None)
    if data_path is None:
        raise ValueError("必须提供 args.data_path 或 args.csv_path")

    train_dataset = MIMICCXRADataset(
        data_path=data_path,
        split="train",
        image_dir=args.image_dir,
        split_dir=split_dir,
        mask_dir=getattr(args, "mask_dir", None),
        transform=transform_train,
        disease_list=disease_list,
        load_masks=load_masks,
        require_masks=require_masks,
        data_format=data_format,
        no_finding_downsample_ratio=no_finding_downsample_ratio,
    )

    val_dataset = MIMICCXRADataset(
        data_path=data_path,
        split="val",
        image_dir=args.image_dir,
        split_dir=split_dir,
        mask_dir=getattr(args, "mask_dir", None),
        transform=transform_val,
        disease_list=train_dataset.disease_list,  # 共享 vocab
        load_masks=load_masks,
        require_masks=require_masks,
        data_format=data_format,
        no_finding_downsample_ratio=no_finding_downsample_ratio,
    )

    test_file_txt = os.path.join(split_dir, "test_image_ids.txt")
    test_file_json = os.path.join(split_dir, "test_indices.json")
    if os.path.exists(test_file_txt) or os.path.exists(test_file_json):
        test_dataset = MIMICCXRADataset(
            data_path=data_path,
            split="test",
            image_dir=args.image_dir,
            split_dir=split_dir,
            mask_dir=getattr(args, "mask_dir", None),
            transform=transform_val,
            disease_list=train_dataset.disease_list,
            load_masks=load_masks,
            require_masks=require_masks,
            data_format=data_format,
            no_finding_downsample_ratio=no_finding_downsample_ratio,
        )
    else:
        print("警告: 未找到 test split 文件，使用 val 作为 test")
        test_dataset = val_dataset

    # 标签映射：优先使用显式 json；否则从 candidates 动态构建
    has_all_map_paths = all([
        severity_to_id_json,
        disease_modifier_to_id_json,
        disease_anatomy_to_id_json,
        os.path.exists(severity_to_id_json or ""),
        os.path.exists(disease_modifier_to_id_json or ""),
        os.path.exists(disease_anatomy_to_id_json or ""),
    ])

    if has_all_map_paths:
        severity_to_id, disease_modifier_to_id, disease_anatomy_to_id = load_label_maps(
            severity_to_id_json=severity_to_id_json,
            disease_modifier_to_id_json=disease_modifier_to_id_json,
            disease_anatomy_to_id_json=disease_anatomy_to_id_json,
        )
    else:
        print("警告: maps/*.json 不完整，改为从 disease_location_candidates.json 动态构建标签映射。")
        severity_to_id, disease_modifier_to_id, disease_anatomy_to_id = build_label_maps_from_candidates(
            split_dir=split_dir,
            disease_list=train_dataset.disease_list,
        )

    collator = MIMICCXRACollator(
        disease_order=train_dataset.disease_list,
        severity_to_id=severity_to_id,
        disease_modifier_to_id=disease_modifier_to_id,
        disease_anatomy_to_id=disease_anatomy_to_id,
        device=device,
    )

    train_loader = data.DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=getattr(args, "num_workers", 0),
        collate_fn=collator,
        pin_memory=True,
    )

    val_loader = data.DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=getattr(args, "num_workers", 0),
        collate_fn=collator,
        pin_memory=True,
    )

    test_loader = data.DataLoader(
        test_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=getattr(args, "num_workers", 0),
        collate_fn=collator,
        pin_memory=True,
    )

    return train_loader, val_loader, test_loader


# -----------------------------
# Minimal test
# -----------------------------
def test_mimic_cxr_dataloader():
    class MockArgs:
        def __init__(self):
            self.data_path = "data/mimic-cxr-a/all_structured_reports.jsonl"
            self.image_dir = "data/mimic-cxr-a/images"
            self.mask_dir = "data/mimic-cxr-a/masks"
            self.batch_size = 4
            self.num_workers = 0

    args = MockArgs()
    split_dir = "data/mimic-cxr-a"

    # 你自己的三个 json 映射路径（示例）
    severity_to_id_json = "data/mimic-cxr-a/maps/severity_to_id.json"
    disease_modifier_to_id_json = "data/mimic-cxr-a/maps/disease_modifier_to_id.json"
    disease_anatomy_to_id_json = "data/mimic-cxr-a/maps/disease_anatomy_to_id.json"

    train_loader, val_loader, test_loader = create_mimic_cxr_data_loaders(
        args=args,
        split_dir=split_dir,
        severity_to_id_json=severity_to_id_json,
        disease_modifier_to_id_json=disease_modifier_to_id_json,
        disease_anatomy_to_id_json=disease_anatomy_to_id_json,
        load_masks=True,
        require_masks=False,  # 设 True 则缺 mask 的样本会被过滤
        data_format="auto",
        device=None,
    )

    batch = next(iter(train_loader))
    print("images:", batch["images"].shape)
    if batch["mask_images"] is not None:
        print("mask_images:", batch["mask_images"].shape)

    labels = batch["labels"]
    for k, v in labels.items():
        print(k, v.shape, v.dtype)

    print("image_ids sample:", batch["image_ids"][:2])
    print("OK")


if __name__ == "__main__":
    test_mimic_cxr_dataloader()
