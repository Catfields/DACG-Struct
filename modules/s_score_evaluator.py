import torch
import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import re

from modules.structured_loss import (
    ProbabilityScoreCalculator, 
    SeverityScoreCalculator, 
    LocationScoreCalculator
)


class SScoresEvaluator:
    """
    S-Score评估器 - 完整的三层评估
    P-Score: 疾病预测准确性
    D-Score: 细节描述精度  
    S-Score: 综合得分
    """
    
    def __init__(
        self,
        disease_list: List[str],
        location_mapper,
        p_weight: float = 0.5,
        d_weight: float = 0.5,
    ):
        self.disease_list = disease_list
        self.disease_to_id = {disease: i for i, disease in enumerate(disease_list)}
        self.location_mapper = location_mapper
        self.p_weight = float(p_weight)
        self.d_weight = float(d_weight)
        
        # 分数计算器
        self.prob_calculator = ProbabilityScoreCalculator()
        self.severity_calculator = SeverityScoreCalculator()
        self.location_calculator = LocationScoreCalculator()
    
    def evaluate_batch(self, predictions: Dict, targets: List[Dict], 
                      disease_threshold: float = 0.3) -> Dict[str, float]:
        """
        批量评估S-Score
        
        Args:
            predictions: 模型预测结果
            targets: 目标标签列表
            disease_threshold: 疾病存在性判断阈值
            
        Returns:
            包含各项S-Score的字典
        """
        #------------调试代码----------------------
        if not hasattr(self, "_debug_printed"):
            print("\n[DEBUG] prediction keys:", list(predictions.keys()))
            for k, v in predictions.items():
                if torch.is_tensor(v):
                    print(f"[DEBUG] {k}: shape={tuple(v.shape)} dtype={v.dtype}")
            self._debug_printed = True
        # -----------------------------------------
        batch_size = len(targets)
        p_scores = []
        d_scores = []
        d_scores_oracle = []
        
        # 解码预测结果
        decoded_predictions = self._decode_predictions(predictions, disease_threshold)
        
        for i in range(batch_size):
            pred = decoded_predictions[i]
            true = targets[i]
            
            # 计算P-Score
            p_score = self.compute_p_score(pred, true)
            p_scores.append(p_score)
            
            # 计算D-Score（仅对正确识别的疾病）
            d_score = self.compute_d_score(pred, true)
            d_scores.append(d_score)

            d_score_oracle = self.compute_d_score_oracle(pred, true)
            d_scores_oracle.append(d_score_oracle)
        
        # 计算平均分数
        avg_p_score = np.mean(p_scores)
        avg_d_score = np.mean(d_scores)
        avg_d_score_oracle = np.mean(d_scores_oracle) if d_scores_oracle else 0.0
        avg_s_score = self.compute_s_score(
            avg_p_score,
            avg_d_score,
            weight_p=self.p_weight,
            weight_d=self.d_weight,
        )
        
        return {
            'P-Score': avg_p_score,
            'D-Score': avg_d_score, 
            'D-Score-oracle': avg_d_score_oracle,
            'S-Score': avg_s_score,
            'P-Score_std': np.std(p_scores),
            'D-Score_std': np.std(d_scores),
            'D-Score-oracle_std': np.std(d_scores_oracle) if d_scores_oracle else 0.0,
        }
    
    def compute_p_score(self, pred: Dict, true: Dict) -> float:
        """
        计算P-Score：疾病预测准确性
        阳性疾病F1 + 阴性疾病F1的综合
        """
        # 获取预测的阳性和阴性疾病
        pred_positive = set(pred['positive_diseases'])
        pred_negative = set(pred['negative_diseases'])
        
        # 获取真实的阳性和阴性疾病
        true_positive = set(true['positive_diseases']) if 'positive_diseases' in true else set()
        true_negative = set(true['negative_diseases']) if 'negative_diseases' in true else set()
        
        # 计算阳性疾病F1
        positive_f1 = self._compute_f1(pred_positive, true_positive)
        
        # 计算阴性疾病F1
        negative_f1 = self._compute_f1(pred_negative, true_negative)
        
        # 综合P-Score（算术平均）
        return (positive_f1 + negative_f1) / 2.0
    
    def compute_d_score(self, pred: Dict, true: Dict) -> float:
        """
        计算D-Score：细节描述精度
        仅针对P-Score中已匹配的疾病
        """
        print("\n[DEBUG] pred positive:", pred['positive_diseases'])
        print("[DEBUG] true positive:", true.get('positive_diseases', []))
        # 找到正确匹配的疾病
        pred_positive = set(pred['positive_diseases'])
        true_positive = set(true['positive_diseases']) if 'positive_diseases' in true else set()
        matched_diseases = pred_positive.intersection(true_positive)
        print("[DEBUG] matched diseases:", matched_diseases)
        
        if not matched_diseases:
            return 0.0
        
        detail_scores = []
        
        # 对每个匹配的疾病计算细节分数
        for disease in matched_diseases:
            # 获取该疾病的预测和真实细节
            pred_details = pred.get('disease_details', {}).get(disease, {})
            true_details = true.get('disease_details', {}).get(disease, {})


            #---调试代码----
            print(f"[DEBUG] disease={disease}")
            print("  pred_details:", pred_details)
            print("  true_details:", true_details)
            if not pred_details or not true_details:
                print("[DEBUG] skip disease due to empty details",
                    "pred_empty=", not pred_details,
                    "true_empty=", not true_details)
                continue
            #---------------------------


            # 计算三个细节项的分数
            scores = []
            
            # 概率分（1 - MSE）
            if 'probability' in pred_details and 'probability' in true_details:
                prob_score = self.prob_calculator.compute_probability_score(
                    pred_details['probability'], true_details['probability']
                )
                scores.append(prob_score)
            
            # 严重程度分（精确匹配）
            if 'severity' in pred_details and 'severity' in true_details:
                severity_score = self.severity_calculator.compute_severity_score(
                    pred_details['severity'], true_details['severity']
                )
                scores.append(severity_score)
            
            # 位置分（BLEU分数）
            if (
                'location' in pred_details
                and 'location' in true_details
                and self.location_mapper is not None
                and hasattr(self.location_mapper, "get_location_name")
            ):
                location_score = self.location_calculator.compute_location_bleu(
                    pred_details['location'], true_details['location'], self.location_mapper
                )
                scores.append(location_score)
            
            if scores:
                print("[DEBUG] raw detail scores:", scores)
                detail_scores.append(np.mean(scores))
        
        return np.mean(detail_scores) if detail_scores else 0.0

    def compute_d_score_oracle(self, pred: Dict, true: Dict) -> float:
        """
        Oracle D-Score：仅评估真实阳性疾病的细节质量，不要求疾病先被预测为阳性。
        用途：当训练早期疾病检出全为空时，仍可观察细节头是否在学习。
        """
        true_positive = set(true['positive_diseases']) if 'positive_diseases' in true else set()
        if not true_positive:
            return 0.0

        detail_scores = []

        for disease in true_positive:
            pred_details = pred.get('disease_details', {}).get(disease, {})
            true_details = true.get('disease_details', {}).get(disease, {})

            if not pred_details or not true_details:
                continue

            scores = []

            if 'probability' in pred_details and 'probability' in true_details:
                prob_score = self.prob_calculator.compute_probability_score(
                    pred_details['probability'], true_details['probability']
                )
                scores.append(prob_score)

            if 'severity' in pred_details and 'severity' in true_details:
                severity_score = self.severity_calculator.compute_severity_score(
                    pred_details['severity'], true_details['severity']
                )
                scores.append(severity_score)

            if (
                'location' in pred_details
                and 'location' in true_details
                and self.location_mapper is not None
                and hasattr(self.location_mapper, "get_location_name")
            ):
                location_score = self.location_calculator.compute_location_bleu(
                    pred_details['location'], true_details['location'], self.location_mapper
                )
                scores.append(location_score)

            if scores:
                detail_scores.append(np.mean(scores))

        return np.mean(detail_scores) if detail_scores else 0.0
    
    def compute_s_score(self, p_score: float, d_score: float, 
                      weight_p: float = 0.5, weight_d: float = 0.5) -> float:
        """
        计算综合S-Score
        结合疾病预测和细节精度
        """
        return weight_p * p_score + weight_d * d_score
    
    def _decode_predictions(self, predictions: Dict, disease_threshold: float = 0.05) -> List[Dict]:
        """
        解码模型预测为可读格式
        """
        expected_num_diseases = len(self.disease_list)
        if expected_num_diseases <= 0:
            raise ValueError(
                f"disease_list 为空，无法解码预测；expected_num_diseases={expected_num_diseases}"
            )

        def _ensure_tensor(name: str) -> torch.Tensor:
            if name not in predictions:
                raise KeyError(name)
            value = predictions[name]
            if not torch.is_tensor(value):
                raise TypeError(
                    f"predictions['{name}'] 必须是 torch.Tensor，但得到: {type(value)}"
                )
            return value

        def _extract_presence_tensor() -> Tuple[str, torch.Tensor, bool]:
            """
            返回 (tensor_desc, tensor, already_prob):
            - already_prob=True 表示 tensor 已经是概率，不需要再 sigmoid/softmax。
            - 对 polarity 张量默认取 positive 通道作为“阳性疾病”概率。
            """
            if 'disease_polarity' in predictions:
                polarity = _ensure_tensor('disease_polarity')
                if polarity.ndim != 3 or polarity.size(-1) != 2:
                    raise ValueError(
                        "predictions['disease_polarity'] 形状非法，期望 (B, *, 2)；"
                        f"shape={tuple(polarity.shape)}, expected_num_diseases={expected_num_diseases}."
                    )
                return "disease_polarity(positive)", polarity[..., 1], True
            if 'polarity_probs' in predictions:
                polarity = _ensure_tensor('polarity_probs')
                if polarity.ndim != 3 or polarity.size(-1) != 2:
                    raise ValueError(
                        "predictions['polarity_probs'] 形状非法，期望 (B, *, 2)；"
                        f"shape={tuple(polarity.shape)}, expected_num_diseases={expected_num_diseases}."
                    )
                return "polarity_probs(positive)", polarity[..., 1], True
            if 'disease_mentions' in predictions:
                return "disease_mentions", _ensure_tensor('disease_mentions'), True
            if 'mention_probs' in predictions:
                return "mention_probs", _ensure_tensor('mention_probs'), True
            if 'disease_logits' in predictions:
                return "disease_logits(sigmoid)", _ensure_tensor('disease_logits'), False
            if 'mention_logits' in predictions:
                return "mention_logits(sigmoid)", _ensure_tensor('mention_logits'), False
            raise ValueError(
                f"无法识别的预测格式：缺少疾病存在性/极性输出键；可用键: {list(predictions.keys())}"
            )

        def _normalize_probs(tensor: torch.Tensor) -> torch.Tensor:
            if tensor.ndim == 0:
                raise ValueError(
                    f"疾病输出张量不应为标量；shape={tuple(tensor.shape)}"
                )
            tensor = tensor.detach()
            if tensor.ndim >= 2 and tensor.shape[-1] == 1:
                tensor = tensor.squeeze(-1)
            if tensor.ndim == 1:
                tensor = tensor.unsqueeze(0)
            return tensor

        # 疾病“阳性”判定优先使用 polarity 的 positive 概率（更贴合多疾病分类语义），否则回退到 mention/logits
        disease_tensor_name, raw_disease_tensor, disease_tensor_is_prob = _extract_presence_tensor()

        raw_disease_tensor = _normalize_probs(raw_disease_tensor)
        disease_scores = raw_disease_tensor if disease_tensor_is_prob else torch.sigmoid(raw_disease_tensor)

        # 将输出统一为 disease 级概率 (B, D)
        best_query_idx: Optional[torch.Tensor] = None  # (B, D)
        num_queries: Optional[int] = None

        if disease_scores.ndim == 2:
            # (B, D) 或 (B, Q)
            batch_size, second_dim = disease_scores.shape
            if second_dim != expected_num_diseases:
                raise ValueError(
                    "疾病存在性输出为二维张量，但第二维既不是 disease 维度也无法推断其语义；"
                    f"tensor='{disease_tensor_name}', shape={tuple(disease_scores.shape)}, "
                    f"expected_num_diseases={expected_num_diseases}. "
                    "若该维度为 query，请输出 (B, Q, D) 形式以支持 query→disease 聚合。"
                )
            disease_probs = disease_scores
        elif disease_scores.ndim == 3:
            # (B, Q, D)
            batch_size, num_queries, last_dim = disease_scores.shape
            if last_dim != expected_num_diseases:
                raise ValueError(
                    "疾病存在性输出为三维张量，但最后一维不是 disease 维度；"
                    f"tensor='{disease_tensor_name}', shape={tuple(disease_scores.shape)}, "
                    f"expected_num_diseases={expected_num_diseases}."
                )
            disease_probs, best_query_idx = disease_scores.max(dim=1)  # (B, D), (B, D)
        else:
            raise ValueError(
                "不支持的疾病存在性输出维度；"
                f"tensor='{disease_tensor_name}', shape={tuple(disease_scores.shape)}, "
                f"expected_num_diseases={expected_num_diseases}. "
                "支持的形状包括: (B, D), (B, D, 1), (B, Q, D), (B, Q)."
            )
        
        batch_size = disease_probs.size(0)
        decoded = []

        def _select_indexed_tensor(
            tensor_name: str,
            batch_index: int,
            disease_index: int,
            query_index: Optional[int],
            expected_diseases: int,
            expected_queries: Optional[int],
            prefer_query: bool = False,
        ) -> torch.Tensor:
            tensor = _ensure_tensor(tensor_name).detach()
            if tensor.ndim < 2:
                raise ValueError(
                    f"predictions['{tensor_name}'] 维度不足以进行索引；shape={tuple(tensor.shape)}"
                )
            if tensor.size(0) != batch_size:
                raise ValueError(
                    f"predictions['{tensor_name}'] batch 维不匹配；"
                    f"shape={tuple(tensor.shape)}, expected_batch_size={batch_size}"
                )

            second_dim = tensor.size(1)
            can_index_by_query = (
                query_index is not None
                and expected_queries is not None
                and second_dim == expected_queries
            )
            can_index_by_disease = (second_dim == expected_diseases)

            if prefer_query and can_index_by_query:
                index = int(query_index)
            elif can_index_by_disease:
                index = disease_index
            elif can_index_by_query:
                index = int(query_index)
            else:
                raise ValueError(
                    f"predictions['{tensor_name}'] 的第二维语义不明确（既不是 disease 也不是 query）；"
                    f"shape={tuple(tensor.shape)}, expected_num_diseases={expected_diseases}, "
                    f"expected_num_queries={expected_queries}. "
                    "请将该张量整理为 (B, D, ...) 或 (B, Q, ...) 并确保与疾病存在性输出一致。"
                )

            return tensor[batch_index, index]
        
        for i in range(batch_size):
            # 解码疾病存在性
            disease_probs_i = disease_probs[i].detach().cpu().numpy()
            
            positive_diseases = []
            negative_diseases = []
            disease_details = {}
            
            for j, prob in enumerate(disease_probs_i):
                disease_name = self.disease_list[j]
                if prob >= disease_threshold:
                    positive_diseases.append(disease_name)
                else:
                    negative_diseases.append(disease_name)

                # 细节预测：为所有疾病填充（便于 oracle D-Score 等分析，不依赖是否预测为阳性）
                details = {}

                query_j: Optional[int] = None
                if best_query_idx is not None:
                    query_j = int(best_query_idx[i, j].item())

                # 概率预测
                if 'disease_probability' in predictions:
                    prob_logits = _select_indexed_tensor(
                        'disease_probability',
                        i,
                        j,
                        query_j,
                        expected_num_diseases,
                        num_queries,
                        prefer_query=(best_query_idx is not None),
                    ).cpu().numpy()
                    pred_prob = np.argmax(prob_logits) + 1  # 转换回1-3
                    details['probability'] = pred_prob
                elif 'prob_logits' in predictions:
                    prob_logits = _select_indexed_tensor(
                        'prob_logits',
                        i,
                        j,
                        query_j,
                        expected_num_diseases,
                        num_queries,
                        prefer_query=(best_query_idx is not None),
                    ).cpu().numpy()
                    pred_prob = np.argmax(prob_logits) + 1
                    details['probability'] = pred_prob

                # 严重程度预测
                if 'disease_severity' in predictions:
                    severity_logits = _select_indexed_tensor(
                        'disease_severity',
                        i,
                        j,
                        query_j,
                        expected_num_diseases,
                        num_queries,
                        prefer_query=(best_query_idx is not None),
                    ).cpu().numpy()
                    pred_severity = np.argmax(severity_logits)
                    details['severity'] = pred_severity
                elif 'sev_logits' in predictions:
                    severity_logits = _select_indexed_tensor(
                        'sev_logits',
                        i,
                        j,
                        query_j,
                        expected_num_diseases,
                        num_queries,
                        prefer_query=(best_query_idx is not None),
                    ).cpu().numpy()
                    pred_severity = np.argmax(severity_logits)
                    details['severity'] = pred_severity

                # 位置预测
                if 'location_probs' in predictions:
                    location_logits = _select_indexed_tensor(
                        'location_probs',
                        i,
                        j,
                        query_j,
                        expected_num_diseases,
                        num_queries,
                        prefer_query=(best_query_idx is not None),
                    ).cpu().numpy()
                    pred_location = int(np.argmax(location_logits))  # 转换为Python int
                    details['location'] = pred_location
                elif 'loc_logits' in predictions:
                    location_logits = _select_indexed_tensor(
                        'loc_logits',
                        i,
                        j,
                        query_j,
                        expected_num_diseases,
                        num_queries,
                        prefer_query=(best_query_idx is not None),
                    ).cpu().numpy()
                    pred_location = int(np.argmax(location_logits))  # 转换为Python int
                    details['location'] = pred_location

                if details:
                    disease_details[disease_name] = details
            
            decoded.append({
                'positive_diseases': positive_diseases,
                'negative_diseases': negative_diseases,
                'disease_details': disease_details
            })
        
        return decoded
    
    def _compute_f1(self, pred_set: set, true_set: set) -> float:
        """计算F1分数"""
        if not pred_set and not true_set:
            return 1.0
        
        if not pred_set or not true_set:
            return 0.0
        
        intersection = pred_set.intersection(true_set)
        precision = len(intersection) / len(pred_set)
        recall = len(intersection) / len(true_set)
        
        if precision + recall == 0:
            return 0.0
        
        return 2 * precision * recall / (precision + recall)
    
    def evaluate_dataset(self, all_predictions: List[Dict], all_targets: List[Dict]) -> Dict:
        """
        评估整个数据集
        """
        total_scores = defaultdict(list)
        
        for pred, target in zip(all_predictions, all_targets):
            p_score = self.compute_p_score(pred, target)
            d_score = self.compute_d_score(pred, target)
            s_score = self.compute_s_score(p_score, d_score)
            
            total_scores['P-Score'].append(p_score)
            total_scores['D-Score'].append(d_score)
            total_scores['S-Score'].append(s_score)
        
        # 计算统计信息
        results = {}
        for metric, scores in total_scores.items():
            results[metric] = {
                'mean': np.mean(scores),
                'std': np.std(scores),
                'min': np.min(scores),
                'max': np.max(scores),
                'median': np.median(scores)
            }
        
        return results
    
    def print_detailed_report(self, results: Dict):
        """打印详细的评估报告"""
        print("=" * 60)
        print("S-Score 详细评估报告")
        print("=" * 60)
        
        for metric, stats in results.items():
            print(f"\n{metric}:")
            print(f"  平均值: {stats['mean']:.4f}")
            print(f"  标准差: {stats['std']:.4f}")
            print(f"  中位数: {stats['median']:.4f}")
            print(f"  最小值: {stats['min']:.4f}")
            print(f"  最大值: {stats['max']:.4f}")
        
        print("\n" + "=" * 60)
        print("评估完成")
        print("=" * 60)
