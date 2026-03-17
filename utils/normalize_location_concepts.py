"""
规范化数据集中的 location 字段

依赖 location_concept_pool_v4.json 进行同义词映射，确保:
1. apical → apex (或 lung_apex，按概念池定义)
2. 修饰词和概念正确分离
3. 修饰词只包含真正的方向/范围词 (left/right/bilateral/diffuse/focal 等)
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Any


def load_concept_pool(pool_path: str) -> Dict:
    """加载概念池"""
    with open(pool_path, 'r', encoding='utf-8') as f:
        pool = json.load(f)
    return pool


def build_synonym_mapping(pool: Dict) -> Dict[str, str]:
    """
    构建同义词映射表

    返回: {synonym: standard_concept}

    特殊处理: 某些词（如 apical）在概念池中被标记为 modifier，
    但实际应该映射到解剖概念
    """
    mapping = {}

    # 特殊映射：解剖前缀词 → 对应的解剖概念
    special_anatomical_mappings = {
        'apical': 'lung_apex',
        'basilar': 'lung_base',
        'basal': 'lung_base',
        'hilar': 'hilum',
        'perihilar': 'perihilar',
        'suprahilar': 'hilum',
        'infrahilar': 'hilum',
        'retrocardiac': 'retrocardiac',
        'hiatal': 'hiatal',
        'costophrenic': 'costophrenic_angle',
        'cardiophrenic': 'cardiophrenic_angle',
    }

    for standard_concept, info in pool.items():
        # 跳过 type=modifier 的概念（通过特殊映射处理）
        if info.get('type') == 'modifier':
            # 但如果是特殊映射中的目标，仍要添加它的同义词
            if standard_concept in special_anatomical_mappings.values():
                for synonym in info.get('synonyms', []):
                    synonym_lower = synonym.lower().strip()
                    if synonym_lower:
                        mapping[synonym_lower] = standard_concept
            continue

        # 添加所有同义词到映射表
        for synonym in info.get('synonyms', []):
            synonym_lower = synonym.lower().strip()
            if synonym_lower:
                mapping[synonym_lower] = standard_concept

    # 添加特殊映射
    for anatomical_prefix, target_concept in special_anatomical_mappings.items():
        mapping[anatomical_prefix] = target_concept

    return mapping


def build_modifier_set(pool: Dict) -> Set[str]:
    """
    构建修饰词集合

    只包括真正的方向/范围修饰词，不包括解剖前缀词
    排除类型: apical, basilar, hilar, perihilar 等解剖相关词
    """
    # 定义应该排除的类型（这些是解剖概念，不应该作为修饰词）
    excluded_types = {
        'lung_apex', 'apical', 'lung_base', 'basilar', 'basal',
        'hilum', 'hilar', 'perihilar', 'suprahilar', 'infrahilar',
        'retrocardiac', 'costophrenic_angle', 'cardiophrenic_angle',
        'hiatal', 'subcarinal', 'paratracheal', 'paraspinal'
    }

    modifiers = set()

    for concept_name, info in pool.items():
        concept_type = info.get('type', '')

        # 跳过解剖相关的类型
        if concept_type in excluded_types:
            continue

        # 只包含真正的修饰词类型
        if concept_type == 'modifier':
            # 进一步排除一些解剖前缀词
            # 这些词虽然 type=modifier，但实际上是解剖位置的描述
            anatomical_prefixes = {
                'apical', 'basilar', 'basal', 'hilar', 'perihilar',
                'suprahilar', 'infrahilar', 'retrocardiac', 'hiatal',
                'costophrenic', 'cardiophrenic'
            }

            # 检查概念名和同义词
            if concept_name.lower() in anatomical_prefixes:
                continue

            for synonym in info.get('synonyms', []):
                if synonym.lower() in anatomical_prefixes:
                    continue

            # 添加概念名本身
            modifiers.add(concept_name.lower())
            # 添加所有同义词
            for synonym in info.get('synonyms', []):
                modifiers.add(synonym.lower())

    return modifiers


def parse_location_raw(
    location_raw: str,
    synonym_mapping: Dict[str, str],
    modifier_set: Set[str]
) -> Dict[str, Any]:
    """
    解析 location_raw 为标准化的 concepts 和 modifiers

    返回:
    {
        'location_concepts': List[str],
        'location_modifiers': List[str],
        'has_location_supervision': bool
    }
    """
    if not location_raw or location_raw.lower() == 'none':
        return {
            'location_concepts': [],
            'location_modifiers': [],
            'has_location_supervision': False
        }

    # 小写并按空格分词
    words = location_raw.lower().split()

    modifiers = []
    concepts = []

    # 逐词处理
    i = 0
    while i < len(words):
        word = words[i]

        # 检查是否为修饰词
        if word in modifier_set:
            modifiers.append(word)
            i += 1
            continue

        # 尝试匹配多词概念（从长到短）
        matched = False
        for length in range(min(4, len(words) - i), 0, -1):
            phrase = ' '.join(words[i:i + length])

            # 检查是否在同义词映射中
            if phrase in synonym_mapping:
                standard_concept = synonym_mapping[phrase]
                concepts.append(standard_concept)
                i += length
                matched = True
                break

        # 如果没有匹配到，尝试单词匹配
        if not matched:
            if word in synonym_mapping:
                standard_concept = synonym_mapping[word]
                concepts.append(standard_concept)
            else:
                # 无法识别的词，作为原始概念保留
                concepts.append(word.replace(' ', '_'))

            i += 1

    # 去重
    modifiers = list(dict.fromkeys(modifiers))
    concepts = list(dict.fromkeys(concepts))

    return {
        'location_concepts': concepts,
        'location_modifiers': modifiers,
        'has_location_supervision': bool(concepts or modifiers)
    }


def normalize_sample(
    sample: Dict[str, Any],
    synonym_mapping: Dict[str, str],
    modifier_set: Set[str]
) -> Dict[str, Any]:
    """规范化单个样本"""
    normalized_sample = {
        'positive_findings': [],
        'negative_findings': sample.get('negative_findings', []),
        'extraction_note': sample.get('extraction_note', ''),
        'metadata': sample.get('metadata', {})
    }

    # 处理 positive_findings
    for finding in sample.get('positive_findings', []):
        location_raw = finding.get('location_raw', '')

        # 重新解析 location
        parsed = parse_location_raw(location_raw, synonym_mapping, modifier_set)

        new_finding = {
            'disease_name': finding.get('disease_name', ''),
            'probability': finding.get('probability', 0),
            'severity': finding.get('severity', 0),
            'location_raw': location_raw,
            'location_concepts': parsed['location_concepts'],
            'location_modifiers': parsed['location_modifiers'],
            'has_location_supervision': parsed['has_location_supervision']
        }

        normalized_sample['positive_findings'].append(new_finding)

    return normalized_sample


def normalize_dataset(
    input_path: str,
    output_path: str,
    synonym_mapping: Dict[str, str],
    modifier_set: Set[str],
    limit: int = None
) -> Dict[str, int]:
    """规范化整个数据集"""

    stats = {
        'total_samples': 0,
        'total_findings': 0,
        'findings_with_supervision': 0,
        'findings_without_supervision': 0,
        'concept_normalized': 0,  # 成功规范化的概念数
        'modifier_extracted': 0,  # 提取的修饰词数
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

            try:
                sample = json.loads(line)

                # 规范化样本
                normalized = normalize_sample(sample, synonym_mapping, modifier_set)

                # 统计
                for finding in normalized['positive_findings']:
                    stats['total_findings'] += 1
                    stats['concept_normalized'] += len(finding['location_concepts'])
                    stats['modifier_extracted'] += len(finding['location_modifiers'])

                    if finding['has_location_supervision']:
                        stats['findings_with_supervision'] += 1
                    else:
                        stats['findings_without_supervision'] += 1

                # 写入
                f_out.write(json.dumps(normalized, ensure_ascii=False) + '\n')

                # 进度
                if stats['total_samples'] % 10000 == 0:
                    print(f"  已处理 {stats['total_samples']} 个样本...")

            except json.JSONDecodeError as e:
                print(f"警告: 行 {line_num + 1} JSON 解析失败: {e}")
                continue
            except Exception as e:
                print(f"警告: 行 {line_num + 1} 处理失败: {e}")
                continue

    return stats


def print_statistics(stats: Dict[str, int]):
    """打印统计信息"""
    print("\n" + "=" * 80)
    print("规范化统计")
    print("=" * 80)

    print(f"\n样本统计:")
    print(f"  总样本数: {stats['total_samples']}")

    print(f"\nFinding 统计:")
    print(f"  总 finding 数: {stats['total_findings']}")
    print(f"  有位置监督: {stats['findings_with_supervision']} ({stats['findings_with_supervision']/max(stats['total_findings'],1)*100:.1f}%)")
    print(f"  无位置监督: {stats['findings_without_supervision']} ({stats['findings_without_supervision']/max(stats['total_findings'],1)*100:.1f}%)")

    print(f"\n规范化统计:")
    print(f"  规范化后的概念总数: {stats['concept_normalized']}")
    print(f"  提取的修饰词总数: {stats['modifier_extracted']}")
    if stats['findings_with_supervision'] > 0:
        print(f"  平均每 finding 概念数: {stats['concept_normalized']/stats['findings_with_supervision']:.2f}")
        print(f"  平均每 finding 修饰词数: {stats['modifier_extracted']/stats['findings_with_supervision']:.2f}")


def test_examples(synonym_mapping: Dict[str, str], modifier_set: Set[str]):
    """测试示例"""
    print("\n" + "=" * 80)
    print("测试示例")
    print("=" * 80)

    test_cases = [
        "bilateral apical",
        "left lung base",
        "right lower lobe",
        "bilateral pleural space",
        "apical",
        "basilar",
        "diffuse lung",
        "focal right upper lobe"
    ]

    for location_raw in test_cases:
        parsed = parse_location_raw(location_raw, synonym_mapping, modifier_set)

        print(f"\n原始: '{location_raw}'")
        print(f"  修饰词: {parsed['location_modifiers']}")
        print(f"  概念: {parsed['location_concepts']}")
        print(f"  有监督: {parsed['has_location_supervision']}")


def main():
    # 文件路径
    concept_pool_path = "location_concept_pool_v4.json"
    input_path = "data/mimic-cxr-a/all_structured_reports_with_location_concepts.jsonl"
    output_path = "data/mimic-cxr-a/all_structured_reports_normalized_v2.jsonl"

    # 检查文件
    if not Path(concept_pool_path).exists():
        print(f"错误: 概念池文件不存在 - {concept_pool_path}")
        return

    if not Path(input_path).exists():
        print(f"错误: 输入文件不存在 - {input_path}")
        return

    # 加载概念池
    print("加载概念池...")
    pool = load_concept_pool(concept_pool_path)
    print(f"  概念总数: {len(pool)}")

    # 构建映射表
    print("\n构建映射表...")
    synonym_mapping = build_synonym_mapping(pool)
    print(f"  同义词映射数: {len(synonym_mapping)}")

    modifier_set = build_modifier_set(pool)
    print(f"  修饰词数: {len(modifier_set)}")

    # 显示一些修饰词示例
    print(f"\n修饰词示例: {sorted(list(modifier_set))[:10]}")

    # 测试示例
    test_examples(synonym_mapping, modifier_set)

    # 规范化数据集
    print(f"\n开始规范化数据集...")
    print(f"  输入: {input_path}")
    print(f"  输出: {output_path}")

    # 创建输出目录
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 执行规范化
    stats = normalize_dataset(input_path, output_path, synonym_mapping, modifier_set, limit=None)

    # 打印统计
    print_statistics(stats)

    print(f"\n完成! 规范化后的数据已保存到: {output_path}")


if __name__ == "__main__":
    main()
