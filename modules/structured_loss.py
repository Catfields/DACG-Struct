"""
向后兼容层：
- 旧代码从 modules.structured_loss 导入 compute_structured_loss
- S-Score 评估器依赖三个打分器类
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.loss import compute_structured_loss, focal_loss, safe_mean


@dataclass
class ProbabilityScoreCalculator:
    """将概率等级差异映射到 [0,1] 分数。"""

    max_level_diff: float = 2.0  # 1..3 级别最大差值为 2

    def compute_probability_score(self, pred_prob: int, true_prob: int) -> float:
        try:
            diff = abs(int(pred_prob) - int(true_prob))
        except Exception:
            return 0.0
        score = 1.0 - min(diff, self.max_level_diff) / self.max_level_diff
        return float(max(0.0, min(1.0, score)))


@dataclass
class SeverityScoreCalculator:
    """严重程度精确匹配评分。"""

    def compute_severity_score(self, pred_severity: int, true_severity: int) -> float:
        try:
            return 1.0 if int(pred_severity) == int(true_severity) else 0.0
        except Exception:
            return 0.0


@dataclass
class LocationScoreCalculator:
    """位置匹配评分（简化版，精确匹配）。"""

    def compute_location_bleu(self, pred_location: int, true_location: int, location_mapper=None) -> float:
        try:
            pred = int(pred_location)
            true = int(true_location)
        except Exception:
            return 0.0
        return 1.0 if pred == true else 0.0

