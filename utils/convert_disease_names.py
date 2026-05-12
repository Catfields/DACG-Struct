"""
统一的疾病名称映射工具

确保全库使用统一的 snake_case 格式疾病名称
"""

# 统一的疾病名称映射（带空格 → snake_case）
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

# 所有疾病列表（snake_case 格式，不含 support_devices）
ALL_DISEASES_SNAKE_CASE = [
    'atelectasis',
    'blunting_of_costophrenic_angle',
    'calcification',
    'cardiomegaly',
    'consolidation',
    'edema',
    'emphysema',
    'enlarged_cardiomediastinum',
    'fracture',
    'granuloma',
    'hernia',
    'lung_lesion',
    'lung_opacity',
    'no_finding',
    'pleural_effusion',
    'pleural_other',
    'pleural_thickening',
    'pneumonia',
    'pneumothorax',
    'scoliosis',
    'tortuosity_of_the_thoracic_aorta',
]


def normalize_disease_name(disease_name: str) -> str:
    """
    标准化疾病名称为 snake_case 格式

    Args:
        disease_name: 原始疾病名称

    Returns:
        snake_case 格式的疾病名称
    """
    if not disease_name:
        return disease_name

    disease_lower = disease_name.strip().lower()
    for original, schema_name in DISEASE_NAME_MAP.items():
        if disease_lower == original.lower():
            return schema_name
    return disease_name.strip()


def normalize_diseases_list(diseases_list: list) -> list:
    """标准化疾病列表"""
    if not isinstance(diseases_list, list):
        return diseases_list
    return [normalize_disease_name(d) for d in diseases_list]
