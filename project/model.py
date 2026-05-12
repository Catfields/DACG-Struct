# project/model.py
# -*- coding: utf-8 -*-

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

import torch
import torch.nn as nn

# project/ 与 modules/ 同级目录，因此直接从 modules 导入
from modules.partition import PartitionModule
from modules.visual_extractor import VisualExtractor
from modules.DualAttentionBlock import DualAttention
from modules.channel_gated import RegionWiseChannelGatedFusion
from modules.moe_region_aggregation import MoERegionAggregation
from modules.GM import GM_Generator
from modules.encoder import V_fused_Encoder
from modules.structured_decoder import StructuredDecoder
from modules.multi_head_classifier import MultiHeadClassifier
import json


@dataclass
class DACGModelConfig:
    visual_extractor: str = "resnet101"
    visual_feat_dim: int = 2048
    visual_extractor_pretrained: bool = False
    d_model: int = 512
    num_regions: int = 4
    vfused_encoder_layers: int = 1
    vfused_encoder_heads: int = 8
    vfused_encoder_d_ff: int = 2048
    vfused_encoder_dropout: float = 0.1
    num_diseases: int = 16
    location_vocab_size: int = -1
    dropout: float = 0.1
    device: str = "auto"
    disease_vocab_sizes: Optional[Dict[str, int]] = None
    disease_order: Optional[List[str]] = None
    disease_json_path: str = "data/mimic-cxr-a/disease_location_candidates.json"

def load_disease_vocab_info(json_path: str):
    """
    从 disease_location_candidates.json 生成 MultiHeadClassifier 需要的三个量：
    - disease_order: list[str]，长度K
    - disease_modifier_vocab_sizes: dict[str,int]，key=疾病名
    - disease_anatomy_vocab_sizes: dict[str,int]，key=疾病名
    """
    with open(json_path, "r") as f:
        data = json.load(f)

    disease_order = list(data.keys())

    # 注意：这里返回 dict，key 是 disease 名称
    disease_modifier_vocab_sizes = {
        d: len(info["modifier_candidates"]) for d, info in data.items()
    }
    disease_anatomy_vocab_sizes = {
        d: len(info["concept_candidates"]) for d, info in data.items()
    }

    return disease_modifier_vocab_sizes, disease_anatomy_vocab_sizes, disease_order

class FullModel(nn.Module):
    """
    完整模型（按顺序组织）：
    1) PartitionModule：原图 + 4个mask分区 -> 5张图
    2) VisualExtractor：提特征 -> global_features + 4个partition_features
    3) DualAttention：仅对 global_features 展平后的token做双注意力融合 -> refined_global_feat
    4) RegionWiseChannelGatedFusion：用 refined_global_feat 对4个region做通道门控 -> 4组门控区域特征
    5) MoERegionAggregation：MoE聚合4个区域 -> V_fused + routing_weights + region_vectors
    6) GM_Generator：V_fused -> Q_guided
    7) Encoder：V_fused -> memory
    8) StructuredDecoder：Q_guided + memory -> Z
    9) MultiHeadClassifier：Z -> 多头输出字典
    """

    def __init__(
        self,
        hidden_dim: int,
        num_queries: int,
        disease_json_path: str,
        **kwargs,
    ):
        super().__init__()
        # 把路径保存下来（方便 debug）
        self.disease_json_path = disease_json_path

        # 在 __init__ 就加载三件套（只做一次）
        dmod_sizes, danat_sizes, disease_order = load_disease_vocab_info(disease_json_path)

        # 让 num_queries 与 disease 数量一致，避免后面 shape 对不上
        if num_queries != len(disease_order):
            print(f"[Warn] num_queries={num_queries} 与 disease_order={len(disease_order)} 不一致，已自动对齐为 {len(disease_order)}")
            num_queries = len(disease_order)
        self.num_queries = num_queries
        # 1) 分区
        self.partition = PartitionModule(**kwargs.get("partition_kwargs", {}))

        # 2) 视觉特征提取
        visual_extractor_kwargs = kwargs.get("visual_extractor_kwargs", {})
        if isinstance(visual_extractor_kwargs, dict):
            visual_extractor_args = SimpleNamespace(**visual_extractor_kwargs)
        else:
            visual_extractor_args = visual_extractor_kwargs
        self.visual_extractor = VisualExtractor(visual_extractor_args)

        # 3) 双注意力（只作用于 global tokens）
        dual_attention_kwargs = kwargs.get("dual_attention_kwargs", {})
        if dual_attention_kwargs:
            self.dual_attention = DualAttention(**dual_attention_kwargs)
        else:
            self.dual_attention = DualAttention()

        # 4) 通道门控融合
        channel_gated_kwargs = {
            "feature_dim": hidden_dim,
            "num_regions": 4,
        }
        channel_gated_kwargs.update(kwargs.get("channel_gated_kwargs", {}))
        self.channel_gated_fusion = RegionWiseChannelGatedFusion(**channel_gated_kwargs)

        # 5) MoE区域聚合
        moe_kwargs = {
            "feature_dim": hidden_dim,
            "num_regions": 4,
        }
        moe_kwargs.update(kwargs.get("moe_kwargs", {}))
        self.moe_region_agg = MoERegionAggregation(**moe_kwargs)

        # 6) 引导查询生成
        gm_kwargs = {
            "num_queries": num_queries,
            "hidden_dim": hidden_dim,
        }
        gm_kwargs.update(kwargs.get("gm_kwargs", {}))
        self.gm_generator = GM_Generator(**gm_kwargs)

        # 7) 编码器
        self.encoder = V_fused_Encoder(
            d_model=hidden_dim,
            **kwargs.get("encoder_kwargs", {}),
        )

        # 8) 解码器
        decoder_kwargs = {"d_model": hidden_dim}
        decoder_kwargs.update(kwargs.get("decoder_kwargs", {}))
        self.decoder = StructuredDecoder(**decoder_kwargs)
        
        # 9) 多头分类器
        self.classifier = MultiHeadClassifier(
            d_model=hidden_dim,
            disease_modifier_vocab_sizes=dmod_sizes,
            disease_anatomy_vocab_sizes=danat_sizes,
            disease_order=disease_order,
            **kwargs.get("classifier_kwargs", {}),
        )

        # 特征维度对齐：把视觉特征通道映射到 hidden_dim(D)
        # 若 VisualExtractor 输出通道 != hidden_dim，用它做投影；相等也不影响
        self.proj = nn.LazyLinear(hidden_dim)

    @staticmethod
    def _featmap_to_tokens(x: torch.Tensor) -> torch.Tensor:
        """
        特征图 (B, C, H', W') -> token序列 (B, M, C)，M=H'*W'
        """
        b, c, h, w = x.shape
        return x.view(b, c, h * w).transpose(1, 2).contiguous()  # (B, M, C)

    def forward(self, original_image: torch.Tensor, binary_masks: torch.Tensor):
        """
        输入:
          - original_image: (B, C, H, W)
          - binary_masks:   (B, 4, H, W)
        输出:
          - MultiHeadClassifier 输出 Dict
        """

        # ---------------------------------------------------------------------
        # 1) Partition：得到5张图 (list)
        # ---------------------------------------------------------------------
        partitioned_images= self.partition(original_image, binary_masks)
        if not isinstance(partitioned_images, (list, tuple)) or len(partitioned_images) != 5:
            raise RuntimeError("PartitionModule 必须返回长度为5的图像列表：原图 + 4张mask分区图")

        # ---------------------------------------------------------------------
        # 2) VisualExtractor：提特征
        # global_features: (B, C_feat, H', W')
        # partition_features: list长度4，每个 (B, C_feat, H', W')
        # ---------------------------------------------------------------------
        global_features, partition_features = self.visual_extractor(partitioned_images)
        if not isinstance(partition_features, (list, tuple)) or len(partition_features) != 4:
            raise RuntimeError("VisualExtractor 必须返回 global_features 和长度为4的 partition_features 列表")

        # 展平 + 投影到 hidden_dim
        global_tokens = self.proj(self._featmap_to_tokens(global_features))  # (B, M, D)
        region_tokens_list = [
            self.proj(self._featmap_to_tokens(x)) for x in partition_features
        ]  # 4 * (B, M, D)

        # ---------------------------------------------------------------------
        # 3) DualAttention：只对 global_tokens 做双注意力融合
        # 输入:  (B, M, D)
        # 输出:  (B, M, D)
        # ---------------------------------------------------------------------
        refined_global = self.dual_attention(global_tokens)  # (B, M, D)

        # ---------------------------------------------------------------------
        # 4) 通道门控融合：用 refined_global 引导4个区域
        # 输入:
        #   - refined_global_feat: (B, M, D)
        #   - region_feats_list:   4个 (B, M, D)
        # 输出:
        #   - fused_region_feats_list: 4个 (B, M, D)
        # ---------------------------------------------------------------------
        fused_region_feats_list = self.channel_gated_fusion(refined_global, region_tokens_list)
        if not isinstance(fused_region_feats_list, (list, tuple)) or len(fused_region_feats_list) != 4:
            raise RuntimeError("RegionWiseChannelGatedFusion 必须输出长度为4的区域特征列表")

        # ---------------------------------------------------------------------
        # 5) MoE区域聚合：融合4个区域 token 序列
        # 输出:
        #   - V_fused: (B, M, D)
        #   - routing_weights: (B, 4)
        #   - region_vectors: (B, 4, D)
        # ---------------------------------------------------------------------
        V_fused, routing_weights, region_vectors = self.moe_region_agg(fused_region_feats_list)

        # ---------------------------------------------------------------------
        # 6) GM：生成引导查询 Q_guided (B, K, D)
        # ---------------------------------------------------------------------
        Q_guided = self.gm_generator(V_fused)

        # ---------------------------------------------------------------------
        # 7) Encoder：得到 memory (B, M, D)
        # ---------------------------------------------------------------------
        memory = self.encoder(V_fused)

        # ---------------------------------------------------------------------
        # 8) Decoder：得到 Z (B, K, D)
        # ---------------------------------------------------------------------
        Z = self.decoder(Q_guided, memory)

        # ---------------------------------------------------------------------
        # 9) MultiHeadClassifier：输出字典
        # ---------------------------------------------------------------------
        outputs = self.classifier(Z)

        # 若训练需要 MoE 的路由信息，可解开下面三行
        # outputs["routing_weights"] = routing_weights
        # outputs["region_vectors"] = region_vectors

        return outputs

    def print_model_info(self) -> None:
        uninitialized = 0
        total_params = 0
        trainable_params = 0
        for p in self.parameters():
            # LazyLinear 在第一次前向前会包含 UninitializedParameter
            if p.__class__.__name__ == "UninitializedParameter":
                uninitialized += 1
                continue
            n = p.numel()
            total_params += n
            if p.requires_grad:
                trainable_params += n
        print("DACG 模型信息:")
        print(f"  disease_json_path: {self.disease_json_path}")
        print(f"  num_queries: {self.num_queries}")
        print(f"  total_params: {total_params:,}")
        print(f"  trainable_params: {trainable_params:,}")
        if uninitialized > 0:
            print(f"  uninitialized_params: {uninitialized} (将在首次 forward 后初始化)")


class DACGModel(FullModel):
    """
    FullModel 的训练入口兼容包装类。
    """

    @classmethod
    def from_config(cls, config: DACGModelConfig) -> "DACGModel":
        if not isinstance(config, DACGModelConfig):
            raise TypeError(f"config 必须是 DACGModelConfig，实际为 {type(config)}")

        disease_json_path = str(config.disease_json_path)
        if not Path(disease_json_path).exists():
            raise FileNotFoundError(
                f"disease_json_path 不存在: {disease_json_path}. "
                "请确认配置中的 model.disease_json_path 或数据目录。"
            )

        num_regions = config.num_regions
        if num_regions != 4:
            print(
                f"[Warn] 当前模型实现固定使用 4 个区域，收到 num_regions={num_regions}，"
                "将自动回退为 4。"
            )
            num_regions = 4

        return cls(
            hidden_dim=config.d_model,
            num_queries=config.num_diseases,
            disease_json_path=disease_json_path,
            visual_extractor_kwargs={
                "visual_extractor": config.visual_extractor,
                "visual_extractor_pretrained": config.visual_extractor_pretrained,
            },
            channel_gated_kwargs={
                "feature_dim": config.d_model,
                "num_regions": num_regions,
            },
            moe_kwargs={
                "feature_dim": config.d_model,
                "num_regions": num_regions,
            },
            gm_kwargs={
                "hidden_dim": config.d_model,
                "num_queries": config.num_diseases,
                "dropout": config.dropout,
            },
            encoder_kwargs={
                "num_layers": config.vfused_encoder_layers,
                "num_heads": config.vfused_encoder_heads,
                "d_ff": config.vfused_encoder_d_ff,
                "dropout": config.vfused_encoder_dropout,
            },
            decoder_kwargs={
                "d_model": config.d_model,
                "nhead": config.vfused_encoder_heads,
                "num_layers": max(1, config.vfused_encoder_layers),
                "dim_feedforward": config.vfused_encoder_d_ff,
                "dropout": config.vfused_encoder_dropout,
            },
        )


if __name__ == "__main__":
    import os
    import random
    import numpy as np
    import torch

    # -----------------------------
    # 0) 固定随机种子，便于复现
    # -----------------------------
    seed = 42
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    # -----------------------------
    # 1) 选择设备
    # -----------------------------
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[Test] device = {device}")

    # -----------------------------
    # 2) 构造假数据（按你定义的输入）
    # -----------------------------
    B, C, H, W = 2, 3, 224, 224
    original_image = torch.randn(B, C, H, W, device=device)

    # binary_masks: (B, 4, H, W)，这里用随机0/1
    binary_masks = (torch.rand(B, 4, H, W, device=device) > 0.5).float()

    # -----------------------------
    # 3) 构造模型
    # -----------------------------
    hidden_dim = 512     # 你项目中的 D
    num_queries = 16     # 你项目中的 K（通常=疾病数量）

    # 如果你的各子模块需要额外参数，可通过 kwargs 传入
    # 例如：
    # model = FullModel(
    #     hidden_dim=hidden_dim,
    #     num_queries=num_queries,
    #     partition_kwargs={...},
    #     visual_extractor_kwargs={...},
    #     dual_attention_kwargs={...},
    #     channel_gated_kwargs={...},
    #     moe_kwargs={...},
    #     gm_kwargs={...},
    #     encoder_kwargs={...},
    #     decoder_kwargs={...},
    #     classifier_kwargs={...},
    # ).to(device)
    disease_json_path='/home/y530/handsome/DACG/data/mimic-cxr-a/disease_location_candidates.json'
    model = FullModel(
        hidden_dim=hidden_dim,
        num_queries=num_queries,
        disease_json_path=disease_json_path
    ).to(device)

    model.eval()

    # -----------------------------
    # 4) 前向测试
    # -----------------------------
    with torch.no_grad():
        outputs = model(original_image, binary_masks)

    # -----------------------------
    # 5) 打印输出结构与张量形状
    # -----------------------------
    if not isinstance(outputs, dict):
        raise RuntimeError(f"MultiHeadClassifier 输出必须是 dict，但得到: {type(outputs)}")

    print("\n[Test] outputs keys:", list(outputs.keys()))

    for k, v in outputs.items():
        if torch.is_tensor(v):
            v_min = float(v.min().cpu())
            v_max = float(v.max().cpu())
            print(f"  - {k:>18s}: shape={tuple(v.shape)}, dtype={v.dtype}, min={v_min:.4f}, max={v_max:.4f}")
        else:
            print(f"  - {k:>18s}: type={type(v)}")

    # -----------------------------
    # 6) 关键shape断言（按你给的接口）
    # -----------------------------
    def _assert_shape(name: str, t: torch.Tensor, expected_prefix: tuple):
        if tuple(t.shape[:len(expected_prefix)]) != expected_prefix:
            raise AssertionError(
                f"[ShapeError] {name} shape={tuple(t.shape)}，但前缀应为 {expected_prefix}"
            )

    # 这些 head 基本都应该是 (B, K, *)
    if "mention_logits" in outputs:
        _assert_shape("mention_logits", outputs["mention_logits"], (B, num_queries))
    if "mention_probs" in outputs:
        _assert_shape("mention_probs", outputs["mention_probs"], (B, num_queries))
    if "polarity_logits" in outputs:
        _assert_shape("polarity_logits", outputs["polarity_logits"], (B, num_queries))
    if "polarity_probs" in outputs:
        _assert_shape("polarity_probs", outputs["polarity_probs"], (B, num_queries))
    if "probability_logits" in outputs:
        _assert_shape("probability_logits", outputs["probability_logits"], (B, num_queries))
    if "severity_logits" in outputs:
        _assert_shape("severity_logits", outputs["severity_logits"], (B, num_queries))
    if "modifier_logits" in outputs:
        _assert_shape("modifier_logits", outputs["modifier_logits"], (B, num_queries))
    if "anatomy_logits" in outputs:
        _assert_shape("anatomy_logits", outputs["anatomy_logits"], (B, num_queries))

    print("\n[Test] ✅ Forward 运行成功，输出 shape 前缀检查通过！")
