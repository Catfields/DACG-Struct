import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Optional, Tuple


class MentionHead(nn.Module):
    """
    Mention head:
    Linear(D → 1) → mention / unknown
    """
    def __init__(self, d_model: int):
        super().__init__()
        self.linear = nn.Linear(d_model, 1)

    def forward(self, z: torch.Tensor):
        """
        Returns:
            mention_logits: (B, K, 1)
            mention_probs:  (B, K, 1) in [0,1]
        """
        mention_logits = self.linear(z)
        mention_probs = torch.sigmoid(mention_logits)
        return mention_logits, mention_probs


class PolarityHead(nn.Module):
    """
    Polarity head:
    Linear(D → 1) → positive / negative
    """
    def __init__(self, d_model: int):
        super().__init__()
        self.linear = nn.Linear(d_model, 1)

    def forward(self, z: torch.Tensor):
        """
        Returns:
            polarity_logits: (B, K, 1)
            polarity_probs:  (B, K, 1) in [0,1] (positive prob)
        """
        polarity_logits = self.linear(z)
        polarity_probs = torch.sigmoid(polarity_logits)
        return polarity_logits, polarity_probs


class ProbabilityHead(nn.Module):
    """Linear(D→3) + softmax → {1,2,3}"""
    def __init__(self, d_model: int):
        super().__init__()
        self.linear = nn.Linear(d_model, 3)

    def forward(self, z: torch.Tensor):
        """
        Returns:
            probability_logits: (B, K, 3)
            probability_probs:  (B, K, 3), rows sum to 1
        """
        probability_logits = self.linear(z)
        probability_probs = torch.softmax(probability_logits, dim=-1)
        return probability_logits, probability_probs


class SeverityHead(nn.Module):
    """Linear(D→S) + softmax → severity class"""
    def __init__(self, d_model: int, severity_levels: int = 4):
        super().__init__()
        self.linear = nn.Linear(d_model, severity_levels)

    def forward(self, z: torch.Tensor):
        """
        Returns:
            severity_logits: (B, K, S)
            severity_probs:  (B, K, S), rows sum to 1
        """
        severity_logits = self.linear(z)
        severity_probs = torch.softmax(severity_logits, dim=-1)
        return severity_logits, severity_probs


class LocationHead(nn.Module):
    """
    Disease-specific Location Head (dual vocab per disease)
    Returns both logits and probs for modifier and anatomy.
    """

    def __init__(
        self,
        d_model: int,
        disease_modifier_vocab_sizes: Dict[str, int],
        disease_anatomy_vocab_sizes: Dict[str, int],
        disease_order: List[str],
    ):
        super().__init__()
        self.d_model = d_model
        self.disease_order = disease_order
        self.num_diseases = len(disease_order)

        for d in disease_order:
            if d not in disease_modifier_vocab_sizes:
                raise ValueError(f"modifier vocab size missing for disease: {d}")
            if d not in disease_anatomy_vocab_sizes:
                raise ValueError(f"anatomy vocab size missing for disease: {d}")

        self.disease_modifier_vocab_sizes = disease_modifier_vocab_sizes
        self.disease_anatomy_vocab_sizes = disease_anatomy_vocab_sizes

        self.modifier_linears = nn.ModuleDict({
            d: nn.Linear(d_model, disease_modifier_vocab_sizes[d])
            for d in disease_order
        })
        self.anatomy_linears = nn.ModuleDict({
            d: nn.Linear(d_model, disease_anatomy_vocab_sizes[d])
            for d in disease_order
        })

        self.max_modifier_vocab_size = max(disease_modifier_vocab_sizes[d] for d in disease_order)
        self.max_anatomy_vocab_size = max(disease_anatomy_vocab_sizes[d] for d in disease_order)

    def forward(self, z: torch.Tensor):
        """
        Returns:
            modifier_logits: (B, K, max_modifier_vocab_size) pad logits=-inf
            modifier_probs:  (B, K, max_modifier_vocab_size) pad probs=0
            anatomy_logits:  (B, K, max_anatomy_vocab_size)  pad logits=-inf
            anatomy_probs:   (B, K, max_anatomy_vocab_size)  pad probs=0
        """
        if z.dim() != 3:
            raise ValueError(f"z 应为 (B,K,D)，但得到 {z.shape}")

        B, K, D = z.shape
        if K != self.num_diseases:
            raise ValueError(f"K 不匹配: 期望 {self.num_diseases}, 实际 {K}")
        if D != self.d_model:
            raise ValueError(f"D 不匹配: 期望 {self.d_model}, 实际 {D}")

        modifier_logits = torch.full(
            (B, K, self.max_modifier_vocab_size),
            float("-inf"),
            dtype=z.dtype,
            device=z.device,
        )
        modifier_probs = torch.zeros(
            (B, K, self.max_modifier_vocab_size),
            dtype=z.dtype,
            device=z.device,
        )

        anatomy_logits = torch.full(
            (B, K, self.max_anatomy_vocab_size),
            float("-inf"),
            dtype=z.dtype,
            device=z.device,
        )
        anatomy_probs = torch.zeros(
            (B, K, self.max_anatomy_vocab_size),
            dtype=z.dtype,
            device=z.device,
        )

        for idx, disease in enumerate(self.disease_order):
            disease_z = z[:, idx:idx + 1, :]  # (B,1,D)

            # modifier
            mod_logits = self.modifier_linears[disease](disease_z)  # (B,1,Vmod)
            mod_probs = torch.softmax(mod_logits, dim=-1)
            Vmod = self.disease_modifier_vocab_sizes[disease]
            modifier_logits[:, idx, :Vmod] = mod_logits.squeeze(1)
            modifier_probs[:, idx, :Vmod] = mod_probs.squeeze(1)

            # anatomy
            anat_logits = self.anatomy_linears[disease](disease_z)  # (B,1,Vanat)
            anat_probs = torch.softmax(anat_logits, dim=-1)
            Vanat = self.disease_anatomy_vocab_sizes[disease]
            anatomy_logits[:, idx, :Vanat] = anat_logits.squeeze(1)
            anatomy_probs[:, idx, :Vanat] = anat_probs.squeeze(1)

        return modifier_logits, modifier_probs, anatomy_logits, anatomy_probs


class MultiHeadClassifier(nn.Module):
    """
    Aggregate 5 heads:
      - MentionHead:      D -> 1 (sigmoid)
      - PolarityHead:     D -> 1 (sigmoid)
      - ProbabilityHead:  D -> 3 (softmax)
      - SeverityHead:     D -> S (softmax)
      - LocationHead:     disease-specific dual vocab (softmax, padded)

    Input:
      z: (B, K, D) where K == len(disease_order)
    Output: dict with logits/probs for each head.
    """

    def __init__(
        self,
        d_model: int,
        disease_modifier_vocab_sizes: Dict[str, int],
        disease_anatomy_vocab_sizes: Dict[str, int],
        disease_order: List[str],
        severity_levels: int = 4,
        gate_by_mention: bool = False,
        mention_gate_threshold: float = 0.5,
    ):
        super().__init__()
        self.d_model = d_model
        self.disease_order = disease_order
        self.severity_levels = severity_levels

        self.gate_by_mention = gate_by_mention
        self.mention_gate_threshold = mention_gate_threshold

        self.mention_head = MentionHead(d_model)
        self.polarity_head = PolarityHead(d_model)
        self.probability_head = ProbabilityHead(d_model)
        self.severity_head = SeverityHead(d_model, severity_levels=severity_levels)
        self.location_head = LocationHead(
            d_model=d_model,
            disease_modifier_vocab_sizes=disease_modifier_vocab_sizes,
            disease_anatomy_vocab_sizes=disease_anatomy_vocab_sizes,
            disease_order=disease_order,
        )

    def forward(self, z: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Args:
            z: (B, K, D)

        Returns dict keys:
            mention_logits:      (B, K, 1)
            mention_probs:       (B, K, 1)
            polarity_logits:     (B, K, 1)
            polarity_probs:      (B, K, 1)
            probability_logits:  (B, K, 3)
            probability_probs:   (B, K, 3)
            severity_logits:     (B, K, S)
            severity_probs:      (B, K, S)
            modifier_logits:     (B, K, Vmod_max)
            modifier_probs:      (B, K, Vmod_max)
            anatomy_logits:      (B, K, Vanat_max)
            anatomy_probs:       (B, K, Vanat_max)

        If gate_by_mention=True:
            - For non-mentioned entries, probs are zeroed (and logits set to -inf for softmax heads).
              Mention head itself is never gated.
        """
        if z.dim() != 3:
            raise ValueError(f"z 应为 (B,K,D)，但得到 {z.shape}")

        B, K, D = z.shape
        if K != len(self.disease_order):
            raise ValueError(f"K 不匹配: 期望 {len(self.disease_order)}, 实际 {K}")
        if D != self.d_model:
            raise ValueError(f"D 不匹配: 期望 {self.d_model}, 实际 {D}")

        out: Dict[str, torch.Tensor] = {}

        # 1) mention
        mention_logits, mention_probs = self.mention_head(z)
        out["mention_logits"] = mention_logits
        out["mention_probs"] = mention_probs

        # 2) polarity
        polarity_logits, polarity_probs = self.polarity_head(z)
        out["polarity_logits"] = polarity_logits
        out["polarity_probs"] = polarity_probs

        # 3) probability
        probability_logits, probability_probs = self.probability_head(z)
        out["probability_logits"] = probability_logits
        out["probability_probs"] = probability_probs

        # 4) severity
        severity_logits, severity_probs = self.severity_head(z)
        out["severity_logits"] = severity_logits
        out["severity_probs"] = severity_probs

        # 5) location (modifier + anatomy)
        modifier_logits, modifier_probs, anatomy_logits, anatomy_probs = self.location_head(z)
        out["modifier_logits"] = modifier_logits
        out["modifier_probs"] = modifier_probs
        out["anatomy_logits"] = anatomy_logits
        out["anatomy_probs"] = anatomy_probs

        # Optional gating by mention
        if self.gate_by_mention:
            # gate mask: (B,K,1) bool
            gate = (mention_probs >= self.mention_gate_threshold)

            # For sigmoid heads (polarity): zero probs when not mentioned; logits set to 0 (or keep as-is)
            out["polarity_probs"] = out["polarity_probs"] * gate.to(out["polarity_probs"].dtype)

            # For softmax heads: set logits to -inf where not mentioned, and probs to 0
            def gate_softmax_logits_and_probs(logits: torch.Tensor, probs: torch.Tensor) -> (torch.Tensor, torch.Tensor):
                # logits: (B,K,C), gate: (B,K,1) -> broadcast
                neg_inf = torch.tensor(float("-inf"), device=logits.device, dtype=logits.dtype)
                gated_logits = torch.where(gate, logits, neg_inf)
                gated_probs = probs * gate.to(probs.dtype)
                return gated_logits, gated_probs

            out["probability_logits"], out["probability_probs"] = gate_softmax_logits_and_probs(
                out["probability_logits"], out["probability_probs"]
            )
            out["severity_logits"], out["severity_probs"] = gate_softmax_logits_and_probs(
                out["severity_logits"], out["severity_probs"]
            )
            out["modifier_logits"], out["modifier_probs"] = gate_softmax_logits_and_probs(
                out["modifier_logits"], out["modifier_probs"]
            )
            out["anatomy_logits"], out["anatomy_probs"] = gate_softmax_logits_and_probs(
                out["anatomy_logits"], out["anatomy_probs"]
            )

        return out


# class LabelMapper:
#     """标签映射器 - 处理各种标签的标准化和转换"""
    
#     @staticmethod
#     def map_probability_to_certainty(probability: int) -> str:
#         """将数值概率映射为诊断确定性等级"""
#         mapping = {
#             1: "低确定性",    # 约18% - 可能/疑似
#             2: "中等确定性",  # 约79% - 很可能/中度确定  
#             3: "高确定性"     # 约1.4% - 肯定/高度确定
#         }
#         return mapping.get(probability, "未知")
    
#     @staticmethod
#     def map_probability_to_score(probability: int) -> float:
#         """将1-3概率映射到0-1范围用于S-Score计算"""
#         return (probability - 1) / 2.0  # 0-1范围
    
#     @staticmethod
#     def normalize_severity(severity_str: str) -> int:
#         """标准化严重程度描述"""
#         severity_mapping = {
#             # 标准类别
#             "None": 0,
#             "mild": 1, 
#             "moderate": 2,
#             "severe": 3,
            
#             # 变体映射到标准类别
#             "very mild": 1,
#             "mild to moderate": 2, 
#             "small to moderate": 2,
#             "large": 3,
#             "marked": 3
#         }
#         return severity_mapping.get(severity_str, 1)  # 默认为mild
    
#     @staticmethod
#     def get_severity_name(severity_id: int) -> str:
#         """获取严重程度名称"""
#         names = ["None", "mild", "moderate", "severe"]
#         return names[severity_id] if 0 <= severity_id < len(names) else "unknown"


# class LocationMapper:
#     """解剖位置映射器 - 标准化解剖位置描述"""
    
#     def __init__(self):
#         self.location_to_id = {}
#         self.id_to_location = {}
#         self.next_id = 0
    
#     def normalize_location(self, location_str) -> int:
#         """标准化解剖位置描述"""
#         if location_str is None or location_str == "None":
#             return self.get_or_add_id("none")
        
#         # 转换为小写并去除首尾空格
#         normalized = str(location_str).lower().strip()
#         return self.get_or_add_id(normalized)
    
#     def get_or_add_id(self, location: str) -> int:
#         """获取或添加位置ID"""
#         if location not in self.location_to_id:
#             self.location_to_id[location] = self.next_id
#             self.id_to_location[self.next_id] = location
#             self.next_id += 1
#         return self.location_to_id[location]
    
#     def get_location_name(self, location_id: int) -> str:
#         """获取位置名称"""
#         return self.id_to_location.get(location_id, "unknown")
    
#     def get_vocab_size(self) -> int:
#         """获取词汇表大小"""
#         return self.next_id


# class StructuredPredictor:
#     """结构化预测器 - 整合所有映射功能"""
    
#     def __init__(self, disease_list: List[str]):
#         self.disease_list = disease_list
#         self.disease_to_id = {disease: i for i, disease in enumerate(disease_list)}
#         self.label_mapper = LabelMapper()
#         self.location_mapper = LocationMapper()
    
#     def process_sample(self, sample: Dict) -> Dict:
#         """处理单个样本为模型输入格式"""
#         # 解析positive_findings
#         positive_info = self._parse_positive_findings(sample['positive_findings'])
        
#         # 解析negative_findings  
#         negative_diseases = sample['negative_findings']
        
#         return {
#             'disease_labels': self._create_disease_labels(
#                 positive_info['diseases'], negative_diseases
#             ),
#             'probability_labels': positive_info['probabilities'],
#             'severity_labels': positive_info['severities'], 
#             'location_labels': positive_info['locations'],
#             'num_findings': len(positive_info['diseases']),
#             # 额外保留正负疾病名称，用于更细粒度的评估（P-Score / D-Score）
#             'positive_diseases': positive_info['diseases'],
#             'negative_diseases': negative_diseases
#         }
    
#     def _parse_positive_findings(self, positive_findings: List[Dict]) -> Dict:
#         """解析positive_findings"""
#         diseases = []
#         probabilities = []
#         severities = []
#         locations = []
        
#         for finding in positive_findings:
#             diseases.append(finding['disease_name'])
#             probabilities.append(finding['probability'])
#             severities.append(self.label_mapper.normalize_severity(finding['severity']))
#             locations.append(self.location_mapper.normalize_location(finding['anatomical_location']))
        
#         return {
#             'diseases': diseases,
#             'probabilities': probabilities,
#             'severities': severities,
#             'locations': locations
#         }
    
#     def _create_disease_labels(self, positive_diseases: List[str], negative_diseases: List[str]) -> List[int]:
#         """创建疾病标签（1=阳性，0=阴性）"""
#         labels = [0] * len(self.disease_list)
        
#         # 标记阳性疾病
#         for disease in positive_diseases:
#             if disease in self.disease_to_id:
#                 labels[self.disease_to_id[disease]] = 1
        
#         # 阴性疾病已经在labels中为0，无需额外处理
        
#         return labels
    
#     def get_disease_vocab_size(self) -> int:
#         """获取疾病词汇表大小"""
#         return len(self.disease_list)
    
#     def get_location_vocab_size(self) -> int:
#         """获取位置词汇表大小"""
#         return self.location_mapper.get_vocab_size()


