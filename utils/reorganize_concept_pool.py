"""
将 location_concept_pool_v3.json 重组为新的格式

新格式:
{
  "concept_name": {
    "synonyms": ["原始术语列表"],
    "type": "解剖/功能区域类型"
  }
}
"""

import json
from pathlib import Path
from collections import defaultdict

# 定义概念类型映射
# 根据解剖概念的功能/位置特征进行分类
ANATOMICAL_TYPE_MAPPING = {
    # 肺部相关
    "lung": "lung",
    "lungs": "lung",
    "pulmonary": "lung",
    "lobe": "lung_lobe",
    "lobes": "lung_lobe",
    "lingula": "lung_lobe",
    "lung base": "lung_base",
    "lung bases": "lung_base",
    "base": "lung_base",
    "bases": "lung_base",
    "basilar": "lung_base",
    "lung apex": "lung_apex",
    "apex": "lung_apex",
    "apices": "lung_apex",
    "apical": "lung_apex",
    "lung apices": "lung_apex",
    "lung field": "lung_field",
    "lung fields": "lung_field",
    "lung zone": "lung_zone",
    "lung zones": "lung_zone",
    "lung region": "lung_region",
    "lung regions": "lung_region",
    "lung areas": "lung_region",
    "lung parenchyma": "lung_parenchyma",
    "interstitial lung": "lung_interstitial",
    "interstitial": "lung_interstitial",
    "parenchyma": "lung_interstitial",
    "parenchymal": "lung_interstitial",
    "interstitium": "lung_interstitial",
    "airspace": "lung_airspace",
    "airspaces": "lung_airspace",
    "alveoli": "lung_airspace",
    "segments": "lung_segment",
    "subsegments": "lung_segment",
    "subsegmental": "lung_segment",
    "segment": "lung_segment",

    # 胸膜相关
    "pleura": "pleural",
    "pleural": "pleural",
    "pleural space": "pleural_space",
    "pleural spaces": "pleural_space",
    "pleural cavity": "pleural_space",
    "pleural cavities": "pleural_space",
    "costophrenic angle": "costophrenic_angle",
    "costophrenic angles": "costophrenic_angle",
    "costophrenic": "costophrenic_angle",
    "cardiophrenic angle": "cardiophrenic_angle",
    "cardiophrenic angles": "cardiophrenic_angle",
    "cardiophrenic": "cardiophrenic_angle",
    "sulcus": "costophrenic_angle",
    "sinus": "pleural_sinus",
    "pleural sinus": "pleural_sinus",
    "pleural plaques": "pleural_plaque",
    "minor fissure": "lung_fissure",
    "major fissure": "lung_fissure",

    # 心血管相关
    "heart": "cardiac",
    "cardiac": "cardiac",
    "cardiac silhouette": "cardiac_silhouette",
    "cardiomediastinal silhouette": "cardiac_silhouette",
    "cardiomediastinum": "cardiac_silhouette",
    "aorta": "aorta",
    "aortic": "aorta",
    "thoracic aorta": "thoracic_aorta",
    "ascending aorta": "ascending_aorta",
    "ascending thoracic aorta": "thoracic_aorta",
    "descending aorta": "descending_aorta",
    "descending thoracic aorta": "thoracic_aorta",
    "aortic arch": "aortic_arch",
    "aortic knob": "aortic_arch",
    "pulmonary vessels": "pulmonary_vascular",
    "pulmonary vascular": "pulmonary_vascular",
    "pulmonary vasculature": "pulmonary_vascular",
    "pulmonary artery": "pulmonary_artery",
    "pulmonary arteries": "pulmonary_artery",
    "main pulmonary artery": "pulmonary_artery",
    "pulmonary interstitium": "lung_interstitial",
    "pulmonary interstitial": "lung_interstitial",
    "atrium": "cardiac_chamber",
    "ventricle": "cardiac_chamber",
    "ventricular": "cardiac_chamber",
    "aortic valve": "cardiac_valve",
    "mitral annulus": "cardiac_valve",
    "mitral annular": "cardiac_valve",
    "svc": "vena_cava",
    "vena cava": "vena_cava",
    "cavoatrial junction": "vena_cava",
    "jugular vein": "jugular_vein",

    # 纵隔相关
    "mediastinum": "mediastinum",
    "mediastinal": "mediastinum",
    "mediastinal contour": "mediastinum",
    "mediastinal lymph nodes": "mediastinum",
    "hila lymph nodes": "hilum",

    # 肺门相关
    "hilum": "hilum",
    "hila": "hilum",
    "hilar": "hilum",
    "hilus": "hilum",
    "perihilar": "perihilar",
    "hilar region": "perihilar",
    "perihilar region": "perihilar",
    "suprahilar": "hilum",
    "suprahilar region": "hilum",
    "infrahilar": "hilum",
    "infrahilar region": "hilum",

    # 心脏后方
    "retrocardiac": "retrocardiac",
    "retrocardiac region": "retrocardiac",
    "retrocardiac area": "retrocardiac",

    # 横膈相关
    "diaphragm": "diaphragm",
    "hemidiaphragm": "diaphragm",
    "hemidiaphragms": "diaphragm",

    # 胸壁/骨骼相关
    "chest wall": "chest_wall",
    "chest": "chest_wall",
    "thorax": "chest_wall",
    "thoracic": "thoracic",
    "thoracic spine": "thoracic_spine",
    "spine": "thoracic_spine",
    "thoracic vertebra": "thoracic_vertebra",
    "thoracic vertebrae": "thoracic_vertebra",
    "thoracic vertebral body": "thoracic_vertebra",
    "thoracic vertebral bodies": "thoracic_vertebra",
    "rib": "rib",
    "ribs": "rib",
    "clavicle": "clavicle",
    "clavicular": "clavicle",
    "sternum": "sternum",
    "sternal": "sternum",
    "scapula": "scapula",
    "humerus": "humerus",
    "humeral head": "humerus",
    "shoulder": "shoulder",
    "thoracolumbar spine": "thoracolumbar_spine",
    "thoracolumbar": "thoracolumbar_spine",
    "thoracolumbar junction": "thoracolumbar_spine",
    "lumbar spine": "lumbar_spine",
    "cervical spine": "cervical_spine",

    # 半胸相关
    "hemithorax": "hemithorax",
    "hemithoraces": "hemithorax",
    "hemi thorax": "hemithorax",
    "side": "hemithorax",
    "left-sided": "hemithorax",
    "right-sided": "hemithorax",

    # 区域相关
    "region": "region",
    "regions": "region",
    "area": "region",
    "areas": "region",
    "zone": "zone",
    "zones": "zone",
    "quadrant": "quadrant",

    # 食管/胃相关
    "esophagus": "esophagus",
    "stomach": "stomach",
    "hiatus": "hiatus",
    "hiatal": "hiatal",
    "hiatal region": "hiatal",
    "gastroesophageal junction": "gastroesophageal_junction",
    "below the diaphragm": "subdiaphragmatic",
    "abdomen": "abdomen",
    "body of the stomach": "stomach",

    # 气管/支气管相关
    "trachea": "trachea",
    "mainstem bronchus": "bronchus",
    "carina": "trachea",
    "above carina": "trachea",
    "above the carina": "trachea",

    # 其他软组织
    "breast": "breast",
    "breasts": "breast",
    "axilla": "axilla",
    "axillary": "axilla",
    "axillary region": "axilla",
    "pectoral": "chest_wall",
    "pectoral region": "chest_wall",
    "subcutaneous": "soft_tissue",
    "neck": "neck",

    # 导管/设备相关位置
    "picc line": "device",
    "picc": "device",
    "central line": "device",
    "chest tube": "device",
    "nasogastric tube": "device",
    "orogastric tube": "device",
    "dialysis catheter": "device",
    "sternotomy": "surgical",
    "sternotomy wires": "surgical",
    "sternal wires": "surgical",
    "midline sternotomy": "surgical",
    "port-a-cath": "device",
    "nasogastric tube in stomach": "device",

    # 其他
    "none": "none",
    "normal": "none",
    "unremarkable": "none",
    "clear": "none",
    " SVC": "vena_cava",
    "low svc": "vena_cava",
}

def get_anatomical_type(term):
    """
    根据术语推断解剖类型
    """
    term_lower = term.lower()

    # 先查找映射表
    if term_lower in ANATOMICAL_TYPE_MAPPING:
        return ANATOMICAL_TYPE_MAPPING[term_lower]

    # 根据关键词推断
    if any(kw in term_lower for kw in ['lung', 'pulmonary', 'lobe', 'lingula']):
        return 'lung'
    elif any(kw in term_lower for kw in ['pleural', 'pleura', 'costophrenic', 'cardiophrenic']):
        return 'pleural'
    elif any(kw in term_lower for kw in ['heart', 'cardiac', 'aorta', 'atrium', 'ventricle']):
        return 'cardiac'
    elif any(kw in term_lower for kw in ['mediastin', 'mediastinal']):
        return 'mediastinum'
    elif any(kw in term_lower for kw in ['hilum', 'hilar', 'hila', 'perihilar', 'suprahilar', 'infrahilar']):
        return 'hilum'
    elif any(kw in term_lower for kw in ['rib', 'clavicle', 'sternum', 'spine', 'vertebra', 'scapula', 'humerus', 'shoulder']):
        return 'skeletal'
    elif any(kw in term_lower for kw in ['chest', 'thorax', 'thoracic']):
        return 'chest_wall'
    elif any(kw in term_lower for kw in ['diaphragm', 'hemidiaphragm']):
        return 'diaphragm'
    elif 'esophagus' in term_lower or 'stomach' in term_lower or 'hiatal' in term_lower:
        return 'abdominal'
    elif 'trachea' in term_lower or 'bronch' in term_lower:
        return 'airway'
    elif 'breast' in term_lower or 'axilla' in term_lower or 'pectoral' in term_lower:
        return 'soft_tissue'
    elif any(kw in term_lower for kw in ['tube', 'line', 'catheter', 'picc', 'port', 'wire', 'device', 'sternotomy']):
        return 'device'
    elif term_lower in ['none', 'normal', 'unremarkable', 'clear']:
        return 'none'
    else:
        return 'other'


def reorganize_concept_pool(input_path, output_path):
    """
    重组概念池
    """
    # 加载原始数据
    print(f"加载概念池: {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        original_pool = json.load(f)

    print(f"  修饰词数量: {len(original_pool.get('modifiers', {}))}")
    print(f"  解剖概念数量: {len(original_pool.get('anatomical_concepts', {}))}")
    print(f"  特殊概念数量: {len(original_pool.get('special_concepts', {}))}")

    # 创建新的概念池
    new_pool = {}

    # 1. 处理修饰词 - 将每个修饰词作为独立概念
    print("\n处理修饰词...")
    for modifier, info in original_pool.get('modifiers', {}).items():
        # 修饰词的 source_terms 就是它的同义词列表
        synonyms = info.get('source_terms', [modifier])
        new_pool[modifier] = {
            "synonyms": synonyms,
            "type": "modifier",
            "frequency": info.get('frequency', 0),
            "disease_count": info.get('disease_count', 0)
        }

    # 2. 处理解剖概念
    print("处理解剖概念...")
    for concept, info in original_pool.get('anatomical_concepts', {}).items():
        synonyms = info.get('source_terms', [concept])

        # 推断类型
        concept_type = get_anatomical_type(concept)

        # 创建标准化的概念名(转换为snake_case)
        standard_name = concept.lower().replace(' ', '_').replace('-', '_')

        new_pool[standard_name] = {
            "synonyms": synonyms,
            "type": concept_type,
            "frequency": info.get('frequency', 0),
            "disease_count": info.get('disease_count', 0)
        }

    # 3. 处理特殊概念(通常是已经合并过的概念)
    print("处理特殊概念...")
    for concept, info in original_pool.get('special_concepts', {}).items():
        synonyms = [concept]  # 特殊概念通常只有一个名称
        concept_type = get_anatomical_type(concept)

        standard_name = concept.lower().replace(' ', '_')
        new_pool[standard_name] = {
            "synonyms": synonyms,
            "type": concept_type,
            "frequency": info.get('frequency', 0),
            "disease_count": info.get('disease_count', 0)
        }

    # 保存新格式
    print(f"\n保存新概念池: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(new_pool, f, indent=2, ensure_ascii=False)

    # 打印统计
    print("\n" + "=" * 80)
    print("重组统计")
    print("=" * 80)
    print(f"总概念数: {len(new_pool)}")

    # 按类型统计
    type_counts = defaultdict(int)
    for concept, info in new_pool.items():
        type_counts[info['type']] += 1

    print("\n按类型统计:")
    for concept_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {concept_type}: {count}")

    # 显示示例
    print("\n[示例概念]")
    print("-" * 80)
    count = 0
    for concept, info in sorted(new_pool.items(), key=lambda x: -x[1].get('frequency', 0)):
        if count >= 20:  # 只显示前20个
            break
        print(f"  {concept}:")
        print(f"    类型: {info['type']}")
        print(f"    同义词: {info['synonyms'][:5]}")  # 只显示前5个
        print(f"    频次: {info['frequency']}")
        count += 1

    return new_pool


if __name__ == "__main__":
    input_file = "location_concept_pool_v3.json"
    output_file = "location_concept_pool_v4.json"

    if not Path(input_file).exists():
        print(f"错误: 文件不存在 - {input_file}")
        exit(1)

    new_pool = reorganize_concept_pool(input_file, output_file)

    print(f"\n完成! 新概念池已保存到: {output_file}")
