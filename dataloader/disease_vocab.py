import json
from typing import Dict, Tuple, Any


def build_disease_vocab_maps_from_json(
    disease_json: Dict[str, Any],
    concept_key: str = "concept_candidates",   # 你的 anatomy/概念
    modifier_key: str = "modifier_candidates", # 你的 modifier
) -> Tuple[
    Dict[str, Dict[str, int]],  # disease_anatomy_to_id
    Dict[str, Dict[str, int]],  # disease_modifier_to_id
    Dict[str, int],             # disease_anatomy_vocab_sizes
    Dict[str, int],             # disease_modifier_vocab_sizes
]:
    """
    将形如:
      disease_json[disease]["concept_candidates"] = [str, str, ...]
      disease_json[disease]["modifier_candidates"] = [str, str, ...]
    转成:
      disease_anatomy_to_id[disease][token] = local_id
      disease_modifier_to_id[disease][token] = local_id
    以及对应 vocab size 字典
    """
    disease_anatomy_to_id: Dict[str, Dict[str, int]] = {}
    disease_modifier_to_id: Dict[str, Dict[str, int]] = {}
    disease_anatomy_vocab_sizes: Dict[str, int] = {}
    disease_modifier_vocab_sizes: Dict[str, int] = {}

    for disease, payload in disease_json.items():
        concepts = payload.get(concept_key, []) or []
        modifiers = payload.get(modifier_key, []) or []

        # 去重但保序（避免 JSON 里偶尔重复）
        def dedup_keep_order(items):
            seen = set()
            out = []
            for x in items:
                if x not in seen:
                    out.append(x)
                    seen.add(x)
            return out

        concepts = dedup_keep_order(concepts)
        modifiers = dedup_keep_order(modifiers)

        disease_anatomy_to_id[disease] = {tok: i for i, tok in enumerate(concepts)}
        disease_modifier_to_id[disease] = {tok: i for i, tok in enumerate(modifiers)}

        disease_anatomy_vocab_sizes[disease] = len(concepts)
        disease_modifier_vocab_sizes[disease] = len(modifiers)

    return (
        disease_anatomy_to_id,
        disease_modifier_to_id,
        disease_anatomy_vocab_sizes,
        disease_modifier_vocab_sizes,
    )


def load_and_build_maps(json_path: str):
    with open(json_path, "r", encoding="utf-8") as f:
        disease_json = json.load(f)
    return build_disease_vocab_maps_from_json(disease_json)

if __name__ == "__main__":
    import sys
    import json

    # ===== 1. 真实 JSON 路径 =====
    if len(sys.argv) >= 2:
        json_path = sys.argv[1]
    else:
        json_path = "/home/y530/handsome/DACG/data/mimic-cxr-a/disease_location_candidates.json"  # 改成你的真实路径

    print(f"[INFO] Loading JSON from: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    (
        disease_anatomy_to_id,
        disease_modifier_to_id,
        disease_anatomy_vocab_sizes,
        disease_modifier_vocab_sizes,
    ) = build_disease_vocab_maps_from_json(raw)

    # ===== 2. 疾病 vocab size 规格表（你的清单）=====
    EXPECTED_VOCAB_SIZES = {
        "atelectasis": (30, 5),
        "calcification": (20, 5),
        "cardiomegaly": (15, 5),
        "consolidation": (30, 5),
        "edema": (20, 5),
        "emphysema": (20, 5),
        "fracture": (30, 5),
        "granuloma": (20, 5),
        "hernia": (15, 5),
        "lung_lesion": (30, 5),
        "lung_opacity": (30, 5),
        "pleural_effusion": (25, 5),
        "pleural_thickening": (25, 5),
        "pneumonia": (30, 5),
        "pneumothorax": (25, 5),
        "tortuosity_of_the_thoracic_aorta": (10, 5),
    }

    # ===== 3. 逐 disease 校验 =====
    errors = []

    for disease, (expected_concept, expected_modifier) in EXPECTED_VOCAB_SIZES.items():
        if disease not in disease_anatomy_vocab_sizes:
            errors.append(f"[MISSING] {disease} not found in JSON")
            continue

        actual_concept = disease_anatomy_vocab_sizes[disease]
        actual_modifier = disease_modifier_vocab_sizes[disease]

        if actual_concept != expected_concept or actual_modifier != expected_modifier:
            errors.append(
                f"[MISMATCH] {disease}: "
                f"concept {actual_concept} (expected {expected_concept}), "
                f"modifier {actual_modifier} (expected {expected_modifier})"
            )

    # ===== 4. 是否有多余 disease（JSON 里有，但规格表没有）=====
    extra_diseases = set(disease_anatomy_vocab_sizes.keys()) - set(EXPECTED_VOCAB_SIZES.keys())
    for disease in sorted(extra_diseases):
        errors.append(f"[EXTRA] {disease} exists in JSON but not in vocab spec")

    # ===== 5. 汇总结果 =====
    if errors:
        print("\n❌ Vocabulary size check FAILED:")
        for e in errors:
            print("  ", e)
        raise AssertionError("Vocabulary size spec check failed")
    else:
        print("\n✅ All diseases match expected vocab sizes!")



