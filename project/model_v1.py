# -*- coding: utf-8 -*-
"""
DACG v1 model.

This is a lean structured generation model that intentionally removes the v2
partition branch, dual attention block, region fusion/MoE stack, and Transformer
encoder. It keeps the output contract used by the existing trainer.
"""

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional
import json

import torch
import torch.nn as nn

from modules.GM import GM_Generator
from modules.multi_head_classifier import MultiHeadClassifier
from modules.structured_decoder import StructuredDecoder
from modules.visual_extractor import build_backbone


@dataclass
class DACGV1ModelConfig:
    visual_extractor: str = "resnet34"
    visual_extractor_pretrained: bool = False
    d_model: int = 256
    decoder_layers: int = 1
    decoder_heads: int = 4
    decoder_d_ff: int = 1024
    decoder_dropout: float = 0.1
    num_diseases: int = 16
    dropout: float = 0.1
    device: str = "auto"
    disease_vocab_sizes: Optional[Dict[str, int]] = None
    disease_order: Optional[List[str]] = None
    disease_json_path: str = "data/mimic-cxr-a/disease_location_candidates.json"


def load_disease_vocab_info(json_path: str):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    disease_order = list(data.keys())
    disease_modifier_vocab_sizes = {
        d: len(info.get("modifier_candidates", [])) for d, info in data.items()
    }
    disease_anatomy_vocab_sizes = {
        d: len(info.get("concept_candidates", [])) for d, info in data.items()
    }
    return disease_modifier_vocab_sizes, disease_anatomy_vocab_sizes, disease_order


class DACGV1Model(nn.Module):
    """
    v1 architecture:
      image -> CNN feature map -> tokens -> GM queries -> StructuredDecoder
      -> MultiHeadClassifier

    Removed from v2:
      - PartitionModule / organ partition extraction
      - DualAttention
      - RegionWiseChannelGatedFusion
      - MoERegionAggregation
      - V_fused_Encoder / Transformer encoder
    """

    def __init__(
        self,
        hidden_dim: int,
        num_queries: int,
        disease_json_path: str,
        visual_extractor_kwargs: Optional[Dict] = None,
        gm_kwargs: Optional[Dict] = None,
        decoder_kwargs: Optional[Dict] = None,
        classifier_kwargs: Optional[Dict] = None,
    ):
        super().__init__()
        self.architecture_version = "v1"
        self.disease_json_path = disease_json_path

        dmod_sizes, danat_sizes, disease_order = load_disease_vocab_info(disease_json_path)
        if num_queries != len(disease_order):
            print(
                f"[Warn][v1] num_queries={num_queries} 与 disease_order={len(disease_order)} 不一致，"
                f"已自动对齐为 {len(disease_order)}"
            )
            num_queries = len(disease_order)
        self.num_queries = num_queries
        self.hidden_dim = hidden_dim

        visual_args = SimpleNamespace(**(visual_extractor_kwargs or {}))
        if not hasattr(visual_args, "visual_extractor"):
            visual_args.visual_extractor = "resnet34"
        if not hasattr(visual_args, "visual_extractor_pretrained"):
            visual_args.visual_extractor_pretrained = False
        self.visual_backbone = build_backbone(
            visual_args.visual_extractor,
            visual_args.visual_extractor_pretrained,
        )

        self.proj = nn.LazyLinear(hidden_dim)

        gm_args = {
            "hidden_dim": hidden_dim,
            "num_queries": num_queries,
        }
        gm_args.update(gm_kwargs or {})
        self.gm_generator = GM_Generator(**gm_args)

        dec_args = {"d_model": hidden_dim}
        dec_args.update(decoder_kwargs or {})
        self.decoder = StructuredDecoder(**dec_args)

        self.classifier = MultiHeadClassifier(
            d_model=hidden_dim,
            disease_modifier_vocab_sizes=dmod_sizes,
            disease_anatomy_vocab_sizes=danat_sizes,
            disease_order=disease_order,
            **(classifier_kwargs or {}),
        )

    @staticmethod
    def _featmap_to_tokens(x: torch.Tensor) -> torch.Tensor:
        b, c, h, w = x.shape
        return x.view(b, c, h * w).transpose(1, 2).contiguous()

    def forward(self, original_image: torch.Tensor, binary_masks: Optional[torch.Tensor] = None):
        # binary_masks is accepted only for trainer compatibility; v1 does not use masks.
        visual_features = self.visual_backbone(original_image)
        memory = self.proj(self._featmap_to_tokens(visual_features))
        q_guided = self.gm_generator(memory)
        z = self.decoder(q_guided, memory)
        return self.classifier(z)

    @classmethod
    def from_config(cls, config) -> "DACGV1Model":
        disease_json_path = str(getattr(config, "disease_json_path", "data/mimic-cxr-a/disease_location_candidates.json"))
        if not Path(disease_json_path).exists():
            raise FileNotFoundError(
                f"disease_json_path 不存在: {disease_json_path}. "
                "请确认配置中的 model.disease_json_path 或数据目录。"
            )

        decoder_layers = getattr(
            config,
            "decoder_layers",
            getattr(config, "vfused_encoder_layers", 1),
        )
        decoder_heads = getattr(
            config,
            "decoder_heads",
            getattr(config, "vfused_encoder_heads", 4),
        )
        decoder_d_ff = getattr(
            config,
            "decoder_d_ff",
            getattr(config, "vfused_encoder_d_ff", 1024),
        )
        decoder_dropout = getattr(
            config,
            "decoder_dropout",
            getattr(config, "vfused_encoder_dropout", getattr(config, "dropout", 0.1)),
        )

        return cls(
            hidden_dim=getattr(config, "d_model", 256),
            num_queries=getattr(config, "num_diseases", 16),
            disease_json_path=disease_json_path,
            visual_extractor_kwargs={
                "visual_extractor": getattr(config, "visual_extractor", "resnet34"),
                "visual_extractor_pretrained": getattr(config, "visual_extractor_pretrained", False),
            },
            gm_kwargs={
                "hidden_dim": getattr(config, "d_model", 256),
                "num_queries": getattr(config, "num_diseases", 16),
                "dropout": getattr(config, "dropout", 0.1),
            },
            decoder_kwargs={
                "d_model": getattr(config, "d_model", 256),
                "nhead": decoder_heads,
                "num_layers": max(1, int(decoder_layers)),
                "dim_feedforward": decoder_d_ff,
                "dropout": decoder_dropout,
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

        print("DACG v1 模型信息:")
        print(f"  disease_json_path: {self.disease_json_path}")
        print("  removed: partition, dual_attention, transformer_encoder")
        print(f"  num_queries: {self.num_queries}")
        print(f"  hidden_dim: {self.hidden_dim}")
        print(f"  total_params: {total_params:,}")
        print(f"  trainable_params: {trainable_params:,}")
        if uninitialized > 0:
            print(f"  uninitialized_params: {uninitialized} (将在首次 forward 后初始化)")


DACGModelV1 = DACGV1Model

