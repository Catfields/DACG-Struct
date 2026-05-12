"""
将 location_concept_pool_v3.json 中的所有疾病名称统一为 snake_case 格式
"""

import json
from pathlib import Path

# 疾病名称映射（与 convert_anatomical_locations.py 中的 DISEASE_NAME_MAP 保持一致）
DISEASE_NAME_MAP = {
    'blunting of costophrenic angle': 'blunting_of_costophrenic_angle',
    'lung opacity': 'lung_opacity',
    'lung lesion': 'lung_lesion',
    'pleural effusion': 'pleural_effusion',
    'pleural thickening': 'pleural_thickening',
    'pleural other': 'pleural_other',
    'tortuosity of the thoracic aorta': 'tortuosity_of_the_thoracic_aorta',
    'enlarged cardiomediastinum': 'enlarged_cardiomediastinum',
    'no finding': 'no_finding',
}


def normalize_disease_name(disease_name: str) -> str:
    """标准化疾病名称"""
    if not disease_name:
        return disease_name
    disease_lower = disease_name.strip().lower()
    for original, schema_name in DISEASE_NAME_MAP.items():
        if disease_lower == original.lower():
            return schema_name
    return disease_name.strip()


def process_diseases_array(diseases_list):
    """处理一个 diseases 数组"""
    if not isinstance(diseases_list, list):
        return diseases_list

    normalized = []
    for disease in diseases_list:
        normalized_disease = normalize_disease_name(disease)
        normalized.append(normalized_disease)
    return normalized


def process_concept_pool(concept_pool):
    """递归处理概念池中的所有 diseases 数组"""

    # 处理 modifiers 部分
    if 'modifiers' in concept_pool:
        for mod_key, mod_info in concept_pool['modifiers'].items():
            if isinstance(mod_info, dict) and 'diseases' in mod_info:
                mod_info['diseases'] = process_diseases_array(mod_info['diseases'])

    # 处理 anatomical_concepts 部分
    if 'anatomical_concepts' in concept_pool:
        for ana_key, ana_info in concept_pool['anatomical_concepts'].items():
            if isinstance(ana_info, dict) and 'diseases' in ana_info:
                ana_info['diseases'] = process_diseases_array(ana_info['diseases'])

    # 处理 special_concepts 部分
    if 'special_concepts' in concept_pool:
        for sp_key, sp_info in concept_pool['special_concepts'].items():
            if isinstance(sp_info, dict) and 'diseases' in sp_info:
                sp_info['diseases'] = process_diseases_array(sp_info['diseases'])

    # 处理 compound_locations 部分（如果存在）
    if 'compound_locations' in concept_pool:
        for cl_key, cl_info in concept_pool['compound_locations'].items():
            if isinstance(cl_info, dict) and 'diseases' in cl_info:
                cl_info['diseases'] = process_diseases_array(cl_info['diseases'])

    return concept_pool


if __name__ == "__main__":
    input_file = "location_concept_pool_v3.json"
    output_file = "location_concept_pool_v3_normalized.json"

    if not Path(input_file).exists():
        print(f"错误: 文件不存在 - {input_file}")
        exit(1)

    # 加载原始文件
    print(f"加载文件: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        concept_pool = json.load(f)

    # 统计原始疾病名称
    original_diseases = set()
    for category in ['modifiers', 'anatomical_concepts', 'special_concepts']:
        if category in concept_pool:
            for item in concept_pool[category].values():
                if 'diseases' in item:
                    original_diseases.update(item['diseases'])

    print(f"原始文件中发现 {len(original_diseases)} 个唯一疾病名称")
    print("原始疾病名称:", sorted(original_diseases))

    # 处理概念池
    print("\n正在标准化疾病名称...")
    normalized_pool = process_concept_pool(concept_pool)

    # 统计标准化后的疾病名称
    normalized_diseases = set()
    for category in ['modifiers', 'anatomical_concepts', 'special_concepts']:
        if category in normalized_pool:
            for item in normalized_pool[category].values():
                if 'diseases' in item:
                    normalized_diseases.update(item['diseases'])

    print(f"标准化后发现 {len(normalized_diseases)} 个唯一疾病名称")
    print("标准化后疾病名称:", sorted(normalized_diseases))

    # 显示转换映射
    print("\n转换映射:")
    for orig, norm in sorted(DISEASE_NAME_MAP.items()):
        if orig in original_diseases:
            print(f"  {orig:40s} → {norm}")

    # 保存标准化后的文件
    print(f"\n保存标准化后的文件: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(normalized_pool, f, indent=2, ensure_ascii=False)

    print("\n完成!")
