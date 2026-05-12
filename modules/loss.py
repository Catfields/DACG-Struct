import torch
import torch.nn.functional as F
from typing import Dict, List, Union, Optional

from dataloader.dataloader import IGNORE_INDEX, construct_labels


def safe_mean(losses: torch.Tensor, mask: torch.Tensor, eps: float = 1e-8) -> torch.Tensor:
    masked_losses = losses * mask
    denom = mask.sum()
    if denom == 0:
        return losses.sum() * 0.0
    return masked_losses.sum() / (denom + eps)


def focal_loss(
    logits: torch.Tensor,
    targets: torch.Tensor,
    alpha: float = 0.75,
    gamma: float = 2.0,
    eps: float = 1e-6,
    max_logit: float = 50.0,
    class_weights: Optional[torch.Tensor] = None,
) -> torch.Tensor:
    logits = torch.nan_to_num(logits, nan=0.0, posinf=max_logit, neginf=-max_logit)
    logits = torch.clamp(logits, -max_logit, max_logit)
    targets = torch.nan_to_num(targets, nan=0.0).to(dtype=logits.dtype).clamp(0, 1)

    bce = F.binary_cross_entropy_with_logits(logits, targets, reduction="none")
    p = torch.sigmoid(logits)
    p_t = p * targets + (1 - p) * (1 - targets)
    alpha_t = alpha * targets + (1 - alpha) * (1 - targets)

    loss = alpha_t * (1 - p_t).pow(gamma) * bce

    if class_weights is not None:
        if targets.dim() == 1:
            weights = class_weights[targets.long()]
        else:
            weights = targets * class_weights[1] + (1 - targets) * class_weights[0]
        loss = loss * weights

    out = loss.mean()
    if not torch.isfinite(out):
        return logits.sum() * 0.0
    return out


def _sanitize_logits_for_ce(logits: torch.Tensor, neg_large: float = -1e4) -> torch.Tensor:
    """
    cross_entropy 不喜欢 -inf / nan：把 -inf 替换成一个大负数
    """
    return torch.nan_to_num(logits, nan=0.0, posinf=0.0, neginf=neg_large)


def _extract_label_tensors(
    labels_or_batch_labels: Union[Dict[str, torch.Tensor], List[Dict]],
    disease_order: List[str],
    severity_to_id: Dict[str, int],
    disease_modifier_to_id: Dict[str, Dict[str, int]],
    disease_anatomy_to_id: Dict[str, Dict[str, int]],
    device: torch.device,
):
    """
    兼容两种输入：
    1) collator 已经构造好的 labels dict（推荐）
    2) 原始 batch_labels（list[dict]），在这里调用 construct_labels 构造
    """
    if isinstance(labels_or_batch_labels, dict):
        labels = labels_or_batch_labels
    else:
        labels = construct_labels(
            batch_labels=labels_or_batch_labels,
            disease_order=disease_order,
            severity_to_id=severity_to_id,
            disease_modifier_to_id=disease_modifier_to_id,
            disease_anatomy_to_id=disease_anatomy_to_id,
            device=device,
        )

    required_keys = [
        "mention_labels",
        "polarity_labels",
        "prob_labels",
        "sev_labels",
        "modifier_labels",
        "anatomy_labels",
        "mask_pol",
        "mask_prob",
        "mask_sev",
        "mask_mod",
        "mask_anat",
    ]
    missing = [k for k in required_keys if k not in labels]
    if missing:
        raise KeyError(f"labels 缺少必要字段: {missing}")

    return (
        labels["mention_labels"].to(device),
        labels["polarity_labels"].to(device),
        labels["prob_labels"].to(device),
        labels["sev_labels"].to(device),
        labels["modifier_labels"].to(device),
        labels["anatomy_labels"].to(device),
        labels["mask_pol"].to(device),
        labels["mask_prob"].to(device),
        labels["mask_sev"].to(device),
        labels["mask_mod"].to(device),
        labels["mask_anat"].to(device),
    )


def compute_structured_loss(
    outputs: Dict[str, torch.Tensor],
    batch_labels: Union[Dict[str, torch.Tensor], List[Dict]],
    disease_order: List[str],
    severity_to_id: Dict[str, int],
    disease_modifier_to_id: Dict[str, Dict[str, int]],
    disease_anatomy_to_id: Dict[str, Dict[str, int]],
    focal_gamma: float = 2.0,
    focal_alpha: float = 0.75,
    eps: float = 1e-6,
    polarity_class_weights: Optional[torch.Tensor] = None,
) -> Dict[str, torch.Tensor]:
    """
    适配 MultiHeadClassifier 输出 dict 的 loss。

    polarity_class_weights: [w_negative, w_positive] 用于 BCE with pos_weight.
    如不提供则使用标准 BCE（无 class weighting）。
    """
    device = outputs["mention_logits"].device

    (
        mention_labels,
        polarity_labels,
        prob_labels,
        sev_labels,
        modifier_labels,
        anatomy_labels,
        mask_pol,
        mask_prob,
        mask_sev,
        mask_mod,
        mask_anat,
    ) = _extract_label_tensors(
        labels_or_batch_labels=batch_labels,
        disease_order=disease_order,
        severity_to_id=severity_to_id,
        disease_modifier_to_id=disease_modifier_to_id,
        disease_anatomy_to_id=disease_anatomy_to_id,
        device=device,
    )

    # ---- 1) mention focal (B,K,1)->(B,K)
    mention_logits = outputs["mention_logits"].squeeze(-1)
    L_mention = focal_loss(
        mention_logits, mention_labels,
        alpha=focal_alpha, gamma=focal_gamma, eps=eps
    )

    # ---- 2) polarity BCE (B,K,1)->(B,K)  with optional class weighting
    polarity_logits = outputs["polarity_logits"].squeeze(-1)
    pol_logits_clean = torch.nan_to_num(polarity_logits, nan=0.0)
    if polarity_class_weights is not None:
        # pos_weight = w_positive / w_negative (for imbalanced data)
        w_neg, w_pos = polarity_class_weights[0].item(), polarity_class_weights[1].item()
        pos_weight = torch.tensor(w_pos / w_neg, device=device)
        pol_loss_per = F.binary_cross_entropy_with_logits(
            pol_logits_clean, polarity_labels, reduction="none", pos_weight=pos_weight
        )
    else:
        pol_loss_per = F.binary_cross_entropy_with_logits(
            pol_logits_clean, polarity_labels, reduction="none"
        )  # (B,K)
    L_polarity = safe_mean(pol_loss_per, mask_pol.float(), eps=eps)
    if not torch.isfinite(L_polarity):
        L_polarity = polarity_logits.sum() * 0.0

    # ---- 3) probability CE (B,K,3)
    prob_logits = _sanitize_logits_for_ce(outputs["probability_logits"])
    prob_loss_per = F.cross_entropy(
        prob_logits.reshape(-1, prob_logits.size(-1)),
        prob_labels.reshape(-1),
        reduction="none",
    ).view_as(prob_labels)  # (B,K)
    L_prob = safe_mean(prob_loss_per, mask_prob.float(), eps=eps)
    if not torch.isfinite(L_prob):
        L_prob = prob_logits.sum() * 0.0

    # ---- 4) severity CE (B,K,S)
    sev_logits = _sanitize_logits_for_ce(outputs["severity_logits"])
    sev_loss_per = F.cross_entropy(
        sev_logits.reshape(-1, sev_logits.size(-1)),
        sev_labels.reshape(-1),
        reduction="none",
    ).view_as(sev_labels)  # (B,K)
    L_severity = safe_mean(sev_loss_per, mask_sev.float(), eps=eps)
    if not torch.isfinite(L_severity):
        L_severity = sev_logits.sum() * 0.0

    # ---- 5) modifier CE (B,K,Vmod_max) with IGNORE + mask
    mod_logits = _sanitize_logits_for_ce(outputs["modifier_logits"])
    mod_loss_flat = F.cross_entropy(
        mod_logits.reshape(-1, mod_logits.size(-1)),
        modifier_labels.reshape(-1),
        ignore_index=IGNORE_INDEX,
        reduction="none",
    )
    mod_loss_per = mod_loss_flat.view_as(modifier_labels)  # (B,K)
    L_modifier = safe_mean(mod_loss_per, mask_mod.float(), eps=eps)
    if not torch.isfinite(L_modifier):
        L_modifier = mod_logits.sum() * 0.0

    # ---- 6) anatomy CE (B,K,Vanat_max) with IGNORE + mask
    anat_logits = _sanitize_logits_for_ce(outputs["anatomy_logits"])
    anat_loss_flat = F.cross_entropy(
        anat_logits.reshape(-1, anat_logits.size(-1)),
        anatomy_labels.reshape(-1),
        ignore_index=IGNORE_INDEX,
        reduction="none",
    )
    anat_loss_per = anat_loss_flat.view_as(anatomy_labels)  # (B,K)
    L_anatomy = safe_mean(anat_loss_per, mask_anat.float(), eps=eps)
    if not torch.isfinite(L_anatomy):
        L_anatomy = anat_logits.sum() * 0.0

    # ---- total
    L_total = (L_mention + L_polarity + L_prob + L_severity + L_modifier + L_anatomy)
    if not torch.isfinite(L_total):
        L_total = mention_logits.sum() * 0.0

    return {
        "total_loss": L_total,
        "mention_loss": L_mention,
        "polarity_loss": L_polarity,
        "probability_loss": L_prob,
        "severity_loss": L_severity,
        "modifier_loss": L_modifier,
        "anatomy_loss": L_anatomy,
    }
