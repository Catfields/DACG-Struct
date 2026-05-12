"""
将原始数据中的 anatomical_location 转换为标准化的 concepts + modifiers 格式

转换规则：
1. 使用 PhraseDecomposer 拆解原始短语
2. 应用同义词映射进行标准化
3. 输出格式：
   - location_raw: 原始位置文本
   - location_modifiers: 标准化修饰词列表
   - location_concepts: 标准化解剖概念列表
   - has_location_supervision: 是否有位置监督信号
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any
import sys

# 导入之前的模块
sys.path.insert(0, str(Path(__file__).parent))
from build_location_concept_pool_v2 import (
    KNOWN_MODIFIERS,
    ANATOMICAL_PREFIX_MODIFIERS,
    SPECIAL_CONCEPT_MAPPINGS,
    COMPOUND_ANATOMICAL_CONCEPTS,
    PhraseDecomposer
)

# 疾病名称映射（将所有带空格的疾病名统一转为 snake_case）
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

# 同义词映射（从之前的结果加载）
SYNONYM_MAPPING = {
    # 修饰词映射
    'modifier_mapping': {
        'both': 'bilateral',
        'bilateral': 'bilateral',
        'bilaterally': 'bilateral',
        'bibasilar': 'basilar',
        'basilar': 'basilar',
        'basal': 'basilar',
        'apex': 'apical',
        'apical': 'apical',
        'apices': 'apical',
        'mid': 'mid',
        'middle': 'mid',
        'medial': 'mid',
        'central': 'mid',
        'lower': 'lower',
        'inferior': 'lower',
        'lowermost': 'lower',
        'upper': 'upper',
        'superior': 'upper',
        'uppermost': 'upper',
        'widespread': 'diffuse',
        'extensive': 'diffuse',
        'diffuse': 'diffuse',
        'generalized': 'diffuse',
        'isolated': 'focal',
        'focal': 'focal',
        'localized': 'focal',
        'multifocal': 'scattered',
        'scattered': 'scattered',
        'patchy': 'scattered',
    },
    # 解剖概念映射
    'anatomical_mapping': {
        'lung': 'lung',
        'lungs': 'lung',
        'pulmonary': 'lung',
        'lobe': 'lobe',
        'lobes': 'lobe',
        'base': 'base',
        'bases': 'base',
        'basilar': 'lung base',
        'basal': 'base',
        'lung base': 'lung base',
        'lung bases': 'lung base',
        'lung bases bilaterally': 'lung base',
        'pleural space': 'pleural space',
        'pleural spaces': 'pleural space',
        'pleural cavity': 'pleural space',
        'pleural cavities': 'pleural space',
        'pleura': 'pleural space',
        'pleural': 'pleural space',
        'costophrenic angle': 'costophrenic angle',
        'costophrenic angles': 'costophrenic angle',
        'costophrenic': 'costophrenic angle',
        'heart': 'heart',
        'cardiac': 'heart',
        'thoracic aorta': 'thoracic aorta',
        'aorta': 'thoracic aorta',
        'descending thoracic aorta': 'thoracic aorta',
        'ascending thoracic aorta': 'thoracic aorta',
        'aortic arch': 'aortic arch',
        'aortic knob': 'aortic arch',
        'rib': 'rib',
        'ribs': 'rib',
        'chest wall': 'chest wall',
        'chest': 'chest wall',
        'thorax': 'chest wall',
        'hemithorax': 'hemithorax',
        'side': 'hemithorax',
        'lung apex': 'lung apex',
        'apex': 'lung apex',
        'apices': 'lung apex',
        'apical': 'lung apex',
        'hilum': 'hilum',
        'hila': 'hilum',
        'hilar': 'hilum',
        'region': 'region',
        'regions': 'region',
        'area': 'region',
        'areas': 'region',
        'retrocardiac': 'retrocardiac',
        'retrocardiac region': 'retrocardiac',
        'retrocardiac area': 'retrocardiac',
        'interstitial': 'interstitial',
        'parenchyma': 'interstitial',
        'parenchymal': 'interstitial',
        'none': 'none',
        'normal': 'none',
        'unremarkable': 'none',
        'clear': 'none',
        'hiatal': 'hiatal',
        'diaphragm': 'hemidiaphragm',
        'hemidiaphragm': 'hemidiaphragm',
        'hemidiaphragms': 'hemidiaphragm',
    }
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


def normalize_location(
    location_text: str,
    decomposer: PhraseDecomposer,
    modifier_mapping: Dict[str, str],
    anatomical_mapping: Dict[str, str]
) -> Dict[str, Any]:
    """
    标准化位置描述

    返回:
    {
        'location_raw': str,
        'location_modifiers': List[str],
        'location_concepts': List[str],
        'has_location_supervision': bool
    }
    """
    if not location_text or location_text.lower() == 'none':
        return {
            'location_raw': location_text,
            'location_modifiers': [],
            'location_concepts': ['none'],
            'has_location_supervision': False
        }

    # 步骤1: 拆解短语
    decomposition = decomposer.decompose(location_text)

    # 步骤2: 标准化修饰词
    normalized_modifiers = []
    for mod in decomposition['modifiers']:
        standard_mod = modifier_mapping.get(mod.lower(), mod)
        normalized_modifiers.append(standard_mod)

    # 去重并保持顺序
    seen = set()
    unique_modifiers = []
    for mod in normalized_modifiers:
        if mod not in seen:
            seen.add(mod)
            unique_modifiers.append(mod)

    # 步骤3: 标准化解剖概念
    anatomical = decomposition['anatomical']
    normalized_concepts = []

    if anatomical:
        standard_anatomical = anatomical_mapping.get(anatomical.lower(), anatomical)
        # 将空格替换为下划线（snake_case）
        standard_anatomical = standard_anatomical.replace(' ', '_')
        normalized_concepts.append(standard_anatomical)

    # 如果既没有修饰词也没有概念，可能是特殊处理的情况
    if not unique_modifiers and not normalized_concepts:
        # 检查是否为纯修饰词（decomposition 未能识别）
        words = location_text.lower().split()
        potential_modifiers = [modifier_mapping.get(w, w) for w in words if w in modifier_mapping]
        if potential_modifiers and len(potential_modifiers) == len(words):
            unique_modifiers = list(dict.fromkeys(potential_modifiers))  # 去重

    # 判断是否有有效的位置监督
    has_supervision = bool(unique_modifiers or normalized_concepts)

    return {
        'location_raw': location_text,
        'location_modifiers': unique_modifiers,
        'location_concepts': normalized_concepts,
        'has_location_supervision': has_supervision
    }


def convert_sample(sample: Dict[str, Any], decomposer: PhraseDecomposer) -> Dict[str, Any]:
    """转换单个样本"""
    converted_sample = {
        'positive_findings': [],
        'negative_findings': [],
        'extraction_note': sample.get('extraction_note', ''),
        'metadata': sample.get('metadata', {})
    }

    # 转换 positive_findings
    for finding in sample.get('positive_findings', []):
        disease_name = finding.get('disease_name', '')
        anatomical_location = finding.get('anatomical_location', '')

        # 标准化疾病名称
        normalized_disease = normalize_disease_name(disease_name)

        # 标准化位置
        location_info = normalize_location(
            anatomical_location,
            decomposer,
            SYNONYM_MAPPING['modifier_mapping'],
            SYNONYM_MAPPING['anatomical_mapping']
        )

        # 构建新的 finding
        new_finding = {
            'disease_name': normalized_disease,
            'probability': finding.get('probability', 0),
            'severity': finding.get('severity', 0),
            'location_raw': location_info['location_raw'],
            'location_modifiers': location_info['location_modifiers'],
            'location_concepts': location_info['location_concepts'],
            'has_location_supervision': location_info['has_location_supervision']
        }

        converted_sample['positive_findings'].append(new_finding)

    # 转换 negative_findings - 标准化疾病名称
    for disease in sample.get('negative_findings', []):
        normalized_disease = normalize_disease_name(disease)
        converted_sample['negative_findings'].append(normalized_disease)

    return converted_sample


def convert_dataset(
    input_path: str,
    output_path: str,
    decomposer: PhraseDecomposer,
    limit: int = None
) -> Dict[str, int]:
    """转换整个数据集"""

    stats = {
        'total_samples': 0,
        'total_findings': 0,
        'successful_conversions': 0,
        'failed_conversions': 0,
        'findings_with_supervision': 0,
        'findings_without_supervision': 0
    }

    with open(input_path, 'r', encoding='utf-8') as f_in, \
         open(output_path, 'w', encoding='utf-8') as f_out:

        for line_num, line in enumerate(f_in):
            if limit and line_num >= limit:
                break

            # 跳过空行
            if not line.strip():
                continue

            stats['total_samples'] += 1

            # 解析原始数据
            try:
                # 每行格式: "序号|JSON内容"
                if '|' in line:
                    _, json_content = line.split('|', 1)
                else:
                    json_content = line

                sample = json.loads(json_content)
            except json.JSONDecodeError as e:
                print(f"警告: 行 {line_num + 1} JSON解析失败: {e}")
                stats['failed_conversions'] += 1
                continue

            # 转换样本
            try:
                converted_sample = convert_sample(sample, decomposer)

                # 统计
                for finding in converted_sample['positive_findings']:
                    stats['total_findings'] += 1
                    if finding['has_location_supervision']:
                        stats['findings_with_supervision'] += 1
                    else:
                        stats['findings_without_supervision'] += 1

                stats['successful_conversions'] += 1

                # 写入转换后的数据
                f_out.write(json.dumps(converted_sample, ensure_ascii=False) + '\n')

                # 进度显示
                if stats['total_samples'] % 1000 == 0:
                    print(f"  已处理 {stats['total_samples']} 个样本...")

            except Exception as e:
                print(f"警告: 行 {line_num + 1} 转换失败: {e}")
                stats['failed_conversions'] += 1

    return stats


def print_statistics(stats: Dict[str, int]):
    """打印统计信息"""
    print("\n" + "=" * 80)
    print("数据转换统计")
    print("=" * 80)

    print(f"\n样本统计:")
    print(f"  总样本数: {stats['total_samples']}")
    print(f"  成功转换: {stats['successful_conversions']}")
    print(f"  失败: {stats['failed_conversions']}")

    print(f"\nFinding 统计:")
    print(f"  总 finding 数: {stats['total_findings']}")
    print(f"  有位置监督: {stats['findings_with_supervision']} ({stats['findings_with_supervision']/max(stats['total_findings'],1)*100:.1f}%)")
    print(f"  无位置监督: {stats['findings_without_supervision']} ({stats['findings_without_supervision']/max(stats['total_findings'],1)*100:.1f}%)")


if __name__ == "__main__":
    input_path = "data/mimic-cxr-a/all_structured_reports_normalized.jsonl"
    output_path = "data/mimic-cxr-a/all_structured_reports_with_location_concepts.jsonl"

    if not Path(input_path).exists():
        print(f"错误: 文件不存在 - {input_path}")
        exit(1)

    print("初始化短语拆解器...")
    decomposer = PhraseDecomposer()

    print(f"开始转换数据集...")
    print(f"  输入: {input_path}")
    print(f"  输出: {output_path}")

    # 创建输出目录
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 转换数据集（可以设置 limit 进行测试）
    stats = convert_dataset(input_path, output_path, decomposer, limit=None)

    # 打印统计
    print_statistics(stats)

    print(f"\n转换完成! 结果已保存到: {output_path}")
