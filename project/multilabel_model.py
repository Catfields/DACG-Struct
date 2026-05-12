# -*- coding: utf-8 -*-
"""
Single-task multi-label DACG model.

This is a separate model entry from project/model.py. It reuses the existing
visual/region/decoder backbone but replaces the five structured heads with one
multi-label classification head.
"""

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, List, Optional

import torch
import torch.nn as nn

from modules.DualAttentionBlock import DualAttention
from modules.GM import GM_Generator
from modules.channel_gated import RegionWiseChannelGatedFusion
from modules.encoder import V_fused_Encoder
from modules.moe_region_aggregation import MoERegionAggregation
from modules.partition import PartitionModule
from modules.structured_decoder import StructuredDecoder
from modules.visual_extractor import VisualExtractor


@dataclass
class MultiLabelDACGModelConfig:
    visual_extractor: str = "resnet101"
    visual_extractor_pretrained: bool = False
    d_model: int = 512
    num_regions: int = 4
    vfused_encoder_layers: int = 1
    vfused_encoder_heads: int = 8
    vfused_encoder_d_ff: int = 2048
    vfused_encoder_dropout: float = 0.1
    dropout: float = 0.1
    num_labels: int = 10
    label_names: Optional[List[str]] = None


class MultiLabelClassifier(nn.Module):
    """One multi-label head over disease queries."""

    def __init__(self, d_model: int, num_labels: int):
        super().__init__()
        self.num_labels = num_labels
        self.linear = nn.Linear(d_model, 1)

    def forward(self, z: torch.Tensor) -> Dict[str, torch.Tensor]:
        if z.dim() != 3:
            raise ValueError(f"z 应为 (B,K,D)，但得到 {tuple(z.shape)}")
        if z.size(1) != self.num_labels:
            raise ValueError(f"K 不匹配: 期望 {self.num_labels}, 实际 {z.size(1)}")
        logits = self.linear(z).squeeze(-1)
        return {
            "logits": logits,
            "probs": torch.sigmoid(logits),
        }


class MultiLabelDACGModel(nn.Module):
    """
    DACG backbone + one multi-label classification head.

    Input:
      original_image: (B,C,H,W)
      binary_masks: (B,4,H,W). For the new dataset masks are optional; the
        trainer supplies zero masks when no segmentation masks exist.

    Output:
      dict(logits=(B,num_labels), probs=(B,num_labels))
    """

    def __init__(
        self,
        hidden_dim: int,
        num_labels: int,
        label_names: Optional[List[str]] = None,
        **kwargs,
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_labels = num_labels
        self.label_names = list(label_names) if label_names is not None else [f"label_{i}" for i in range(num_labels)]

        self.partition = PartitionModule(**kwargs.get("partition_kwargs", {}))

        visual_extractor_kwargs = kwargs.get("visual_extractor_kwargs", {})
        if isinstance(visual_extractor_kwargs, dict):
            visual_extractor_args = SimpleNamespace(**visual_extractor_kwargs)
        else:
            visual_extractor_args = visual_extractor_kwargs
        self.visual_extractor = VisualExtractor(visual_extractor_args)

        dual_attention_kwargs = kwargs.get("dual_attention_kwargs", {})
        self.dual_attention = DualAttention(**dual_attention_kwargs) if dual_attention_kwargs else DualAttention()

        channel_gated_kwargs = {"feature_dim": hidden_dim, "num_regions": 4}
        channel_gated_kwargs.update(kwargs.get("channel_gated_kwargs", {}))
        self.channel_gated_fusion = RegionWiseChannelGatedFusion(**channel_gated_kwargs)

        moe_kwargs = {"feature_dim": hidden_dim, "num_regions": 4}
        moe_kwargs.update(kwargs.get("moe_kwargs", {}))
        self.moe_region_agg = MoERegionAggregation(**moe_kwargs)

        gm_kwargs = {"num_queries": num_labels, "hidden_dim": hidden_dim}
        gm_kwargs.update(kwargs.get("gm_kwargs", {}))
        self.gm_generator = GM_Generator(**gm_kwargs)

        self.encoder = V_fused_Encoder(
            d_model=hidden_dim,
            **kwargs.get("encoder_kwargs", {}),
        )

        decoder_kwargs = {"d_model": hidden_dim}
        decoder_kwargs.update(kwargs.get("decoder_kwargs", {}))
        self.decoder = StructuredDecoder(**decoder_kwargs)

        self.classifier = MultiLabelClassifier(hidden_dim, num_labels)
        self.proj = nn.LazyLinear(hidden_dim)

    @staticmethod
    def _featmap_to_tokens(x: torch.Tensor) -> torch.Tensor:
        b, c, h, w = x.shape
        return x.view(b, c, h * w).transpose(1, 2).contiguous()

    def forward(self, original_image: torch.Tensor, binary_masks: torch.Tensor) -> Dict[str, torch.Tensor]:
        partitioned_images = self.partition(original_image, binary_masks)
        if not isinstance(partitioned_images, (list, tuple)) or len(partitioned_images) != 5:
            raise RuntimeError("PartitionModule 必须返回长度为5的图像列表：原图 + 4张mask分区图")

        global_features, partition_features = self.visual_extractor(partitioned_images)
        if not isinstance(partition_features, (list, tuple)) or len(partition_features) != 4:
            raise RuntimeError("VisualExtractor 必须返回 global_features 和长度为4的 partition_features 列表")

        global_tokens = self.proj(self._featmap_to_tokens(global_features))
        region_tokens_list = [self.proj(self._featmap_to_tokens(x)) for x in partition_features]

        refined_global = self.dual_attention(global_tokens)
        fused_region_feats_list = self.channel_gated_fusion(refined_global, region_tokens_list)
        V_fused, _, _ = self.moe_region_agg(fused_region_feats_list)
        Q_guided = self.gm_generator(V_fused)
        memory = self.encoder(V_fused)
        Z = self.decoder(Q_guided, memory)

        return self.classifier(Z)

    @classmethod
    def from_config(cls, config: MultiLabelDACGModelConfig) -> "MultiLabelDACGModel":
        if not isinstance(config, MultiLabelDACGModelConfig):
            raise TypeError(f"config 必须是 MultiLabelDACGModelConfig，实际为 {type(config)}")

        num_regions = config.num_regions
        if num_regions != 4:
            print(f"[Warn] 当前模型实现固定使用 4 个区域，收到 num_regions={num_regions}，将自动回退为 4。")
            num_regions = 4

        return cls(
            hidden_dim=config.d_model,
            num_labels=config.num_labels,
            label_names=config.label_names,
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
                "num_queries": config.num_labels,
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

    def print_model_info(self) -> None:
        uninitialized = 0
        total_params = 0
        trainable_params = 0
        for p in self.parameters():
            if p.__class__.__name__ == "UninitializedParameter":
                uninitialized += 1
                continue
            n = p.numel()
            total_params += n
            if p.requires_grad:
                trainable_params += n

        print("MultiLabel DACG 模型信息:")
        print(f"  num_labels: {self.num_labels}")
        print(f"  labels: {self.label_names}")
        print(f"  total_params: {total_params:,}")
        print(f"  trainable_params: {trainable_params:,}")
        if uninitialized > 0:
            print(f"  uninitialized_params: {uninitialized} (将在首次 forward 后初始化)")
