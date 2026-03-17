"""
将每条原始短语映射成标准化的 (修饰词, 解剖概念) 组合并重新计数

处理流程：
1. 加载原始的 disease-phrase-counts 数据
2. 使用概念池拆解器分解每个短语
3. 应用同义词映射，将修饰词和解剖概念标准化
4. 生成标准化的 (修饰词, 解剖概念) 组合
5. 按疾病统计每个标准概念的频次
"""

import json
import csv
from collections import defaultdict, Counter
from pathlib import Path
import sys

# 导入拆解器
sys.path.insert(0, str(Path(__file__).parent))
from build_location_concept_pool_v2 import (
    KNOWN_MODIFIERS,
    ANATOMICAL_PREFIX_MODIFIERS,
    SPECIAL_CONCEPT_MAPPINGS,
    COMPOUND_ANATOMICAL_CONCEPTS,
    PhraseDecomposer
)


def load_synonym_mapping(mapping_path):
    """加载同义词映射表"""
    with open(mapping_path, 'r', encoding='utf-8') as f:
        mapping = json.load(f)
    return mapping['modifier_mapping'], mapping['anatomical_mapping']


def load_original_phrases(csv_path):
    """加载原始的 disease-phrase-counts 数据"""
    disease_phrases = defaultdict(list)

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            disease = row['disease']
            phrase = row['phrase']
            count = int(row['count'])
            disease_phrases[disease].append((phrase, count))

    return disease_phrases


def normalize_phrase(phrase, decomposer, modifier_mapping, anatomical_mapping):
    """
    标准化短语为 (修饰词, 解剖概念) 元组

    返回: {
        'modifiers': [标准化修饰词列表],
        'anatomical': 标准化解剖概念,
        'original': 原始短语,
        'decomposition': 拆解结果
    }
    """
    # 步骤1: 拆解短语
    decomposition = decomposer.decompose(phrase)

    # 步骤2: 标准化修饰词
    normalized_modifiers = []
    for mod in decomposition['modifiers']:
        # 应用同义词映射
        standard_mod = modifier_mapping.get(mod.lower(), mod)
        normalized_modifiers.append(standard_mod)

    # 步骤3: 标准化解剖概念
    anatomical = decomposition['anatomical']
    if anatomical:
        standard_anatomical = anatomical_mapping.get(anatomical.lower(), anatomical)
    else:
        standard_anatomical = ''

    return {
        'modifiers': normalized_modifiers,
        'anatomical': standard_anatomical,
        'original': phrase,
        'decomposition': decomposition
    }


def create_concept_key(modifiers, anatomical):
    """
    创建概念键，用于计数
    格式: "(mod1,mod2, anatomical)" 或 "(mod1,mod2,)" 或 "(,anatomical)"
    """
    if not modifiers and not anatomical:
        return "(,)"

    mod_str = ','.join(sorted(set(modifiers))) if modifiers else ''
    return f"({mod_str},{anatomical})"


def normalize_and_count(disease_phrases, decomposer, modifier_mapping, anatomical_mapping):
    """
    标准化所有短语并重新计数

    返回: {
        'disease_concepts': {disease: {concept_key: count}},
        'global_concepts': {concept_key: count},
        'concept_details': {concept_key: {'modifiers': [], 'anatomical': '', 'examples': []}}
    }
    """
    disease_concepts = defaultdict(lambda: defaultdict(int))
    global_concepts = Counter()
    concept_details = defaultdict(lambda: {
        'modifiers': [],
        'anatomical': '',
        'examples': [],
        'diseases': set()
    })

    # 统计信息
    stats = {
        'total_phrases': 0,
        'successful_normalizations': 0,
        'failed_normalizations': 0,
        'modifier_only': 0,
        'anatomical_only': 0,
        'mixed': 0
    }

    for disease, phrases in disease_phrases.items():
        for phrase, count in phrases:
            stats['total_phrases'] += 1

            try:
                # 标准化短语
                normalized = normalize_phrase(
                    phrase,
                    decomposer,
                    modifier_mapping,
                    anatomical_mapping
                )

                # 创建概念键
                concept_key = create_concept_key(
                    normalized['modifiers'],
                    normalized['anatomical']
                )

                # 计数
                disease_concepts[disease][concept_key] += count
                global_concepts[concept_key] += count

                # 记录详情
                details = concept_details[concept_key]
                details['modifiers'] = normalized['modifiers']
                details['anatomical'] = normalized['anatomical']
                details['diseases'].add(disease)

                # 添加示例（最多保留5个）
                if len(details['examples']) < 5:
                    details['examples'].append(f"{phrase} ({count})")

                # 统计
                has_mod = bool(normalized['modifiers'])
                has_ana = bool(normalized['anatomical'])

                if has_mod and has_ana:
                    stats['mixed'] += 1
                elif has_mod:
                    stats['modifier_only'] += 1
                elif has_ana:
                    stats['anatomical_only'] += 1

                stats['successful_normalizations'] += 1

            except Exception as e:
                print(f"警告: 标准化失败 - {phrase}: {e}")
                stats['failed_normalizations'] += 1

    # 转换set为sorted list
    for key in concept_details:
        concept_details[key]['diseases'] = sorted(concept_details[key]['diseases'])

    return {
        'disease_concepts': dict(disease_concepts),
        'global_concepts': global_concepts,
        'concept_details': dict(concept_details),
        'stats': stats
    }


def save_results(results, output_dir):
    """保存标准化结果"""

    # 过滤掉 support devices 和 no finding 的数据
    excluded_diseases = {'support devices', 'no finding'}

    # 过滤后的全局概念计数（只包含真实疾病）
    disease_filtered_global = Counter()
    for concept_key, count in results['global_concepts'].items():
        details = results['concept_details'][concept_key]
        # 只统计真实疾病的贡献
        filtered_count = 0
        for disease in details['diseases']:
            if disease not in excluded_diseases:
                # 估算：按疾病数平均分配
                filtered_count += count // len(details['diseases'])
        if filtered_count > 0:
            disease_filtered_global[concept_key] = filtered_count

    # 1. 保存全局概念计数（仅真实疾病）
    with open(output_dir / 'normalized_concept_counts.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['concept_key', 'modifiers', 'anatomical', 'total_count', 'disease_count', 'examples'])

        for concept_key, count in sorted(disease_filtered_global.items(), key=lambda x: -x[1]):
            details = results['concept_details'][concept_key]
            # 过滤后的疾病列表
            filtered_diseases = [d for d in details['diseases'] if d not in excluded_diseases]
            if not filtered_diseases:
                continue

            modifiers_str = '; '.join(details['modifiers']) if details['modifiers'] else ''
            examples_str = ' | '.join(details['examples'][:3])
            diseases_str = '; '.join(filtered_diseases)

            writer.writerow([
                concept_key,
                modifiers_str,
                details['anatomical'],
                count,
                len(filtered_diseases),
                examples_str
            ])
    print(f"✓ 全局概念计数已保存（已排除support devices和no finding）: normalized_concept_counts.csv")

    # 2. 保存按疾病分组的计数（仅真实疾病）
    with open(output_dir / 'normalized_concept_counts_by_disease.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['disease', 'concept_key', 'modifiers', 'anatomical', 'count'])

        for disease in sorted(results['disease_concepts'].keys()):
            if disease in excluded_diseases:
                continue
            concepts = results['disease_concepts'][disease]
            for concept_key, count in sorted(concepts.items(), key=lambda x: -x[1]):
                details = results['concept_details'][concept_key]
                modifiers_str = '; '.join(details['modifiers']) if details['modifiers'] else ''

                writer.writerow([
                    disease,
                    concept_key,
                    modifiers_str,
                    details['anatomical'],
                    count
                ])
    print(f"✓ 按疾病分组的计数已保存（已排除support devices和no finding）: normalized_concept_counts_by_disease.csv")

    # 3. 保存 support devices 的单独统计
    if 'support devices' in results['disease_concepts']:
        with open(output_dir / 'support_devices_concepts.csv', 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['concept_key', 'modifiers', 'anatomical', 'count', 'examples'])

            concepts = results['disease_concepts']['support devices']
            for concept_key, count in sorted(concepts.items(), key=lambda x: -x[1]):
                details = results['concept_details'][concept_key]
                modifiers_str = '; '.join(details['modifiers']) if details['modifiers'] else ''
                examples_str = ' | '.join(details['examples'][:3])

                writer.writerow([
                    concept_key,
                    modifiers_str,
                    details['anatomical'],
                    count,
                    examples_str
                ])
        print(f"✓ support devices 概念统计已保存: support_devices_concepts.csv")

    # 4. 保存 no finding 的单独统计
    if 'no finding' in results['disease_concepts']:
        with open(output_dir / 'no_finding_concepts.csv', 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['concept_key', 'modifiers', 'anatomical', 'count', 'examples'])

            concepts = results['disease_concepts']['no finding']
            for concept_key, count in sorted(concepts.items(), key=lambda x: -x[1]):
                details = results['concept_details'][concept_key]
                modifiers_str = '; '.join(details['modifiers']) if details['modifiers'] else ''
                examples_str = ' | '.join(details['examples'][:3])

                writer.writerow([
                    concept_key,
                    modifiers_str,
                    details['anatomical'],
                    count,
                    examples_str
                ])
        print(f"✓ no finding 概念统计已保存: no_finding_concepts.csv")

    # 5. 保存JSON格式的完整结果
    # 分别保存真实疾病、support devices、no finding
    disease_only_concepts = {
        k: v for k, v in results['disease_concepts'].items()
        if k not in excluded_diseases
    }

    # 过滤全局概念的疾病列表
    filtered_global_concepts = []
    for key, count in results['global_concepts'].most_common():
        details = results['concept_details'][key].copy()
        details['diseases'] = [d for d in details['diseases'] if d not in excluded_diseases]
        if details['diseases']:
            filtered_global_concepts.append({
                'key': key,
                'count': count,
                'details': details
            })

    json_output = {
        'stats': results['stats'],
        'excluded_diseases': list(excluded_diseases),
        'disease_only': {
            'global_concepts': filtered_global_concepts,
            'disease_concepts': disease_only_concepts
        },
        'support_devices': results['disease_concepts'].get('support devices', {}),
        'no_finding': results['disease_concepts'].get('no finding', {})
    }

    with open(output_dir / 'normalized_concept_counts.json', 'w', encoding='utf-8') as f:
        json.dump(json_output, f, indent=2, ensure_ascii=False)
    print(f"✓ JSON格式结果已保存: normalized_concept_counts.json")


def print_summary(results):
    """打印统计摘要"""

    print("\n" + "=" * 80)
    print("标准化概念计数摘要（已隔离 support devices 和 no finding）")
    print("=" * 80)

    stats = results['stats']
    excluded_diseases = {'support devices', 'no finding'}

    print(f"\n处理统计:")
    print(f"  总短语数: {stats['total_phrases']}")
    print(f"  成功标准化: {stats['successful_normalizations']}")
    print(f"  失败: {stats['failed_normalizations']}")

    print(f"\n数据隔离:")
    print(f"  真实疾病数量: {len([d for d in results['disease_concepts'].keys() if d not in excluded_diseases])}")
    print(f"  隔离项目: support devices, no finding")

    # 统计各项目的概念数量
    sd_concepts = results['disease_concepts'].get('support devices', {})
    nf_concepts = results['disease_concepts'].get('no finding', {})
    disease_concepts = {k: v for k, v in results['disease_concepts'].items() if k not in excluded_diseases}

    print(f"\n各项目概念数量:")
    print(f"  support devices: {len(sd_concepts)} 个概念")
    print(f"  no finding: {len(nf_concepts)} 个概念")
    print(f"  真实疾病总计: {sum(len(v) for v in disease_concepts.values())} 个概念")

    # 过滤后的全局概念
    filtered_global = Counter()
    for concept_key, count in results['global_concepts'].items():
        details = results['concept_details'][concept_key]
        filtered_diseases = [d for d in details['diseases'] if d not in excluded_diseases]
        if filtered_diseases:
            # 重新估算计数
            filtered_global[concept_key] = count * len(filtered_diseases) // len(details['diseases'])

    print(f"\n全局概念统计（仅真实疾病）:")
    print(f"  唯一概念数: {len(filtered_global)}")

    print(f"\n概念类型分布:")
    print(f"  纯修饰词 (如 bilateral): {stats['modifier_only']}")
    print(f"  纯解剖概念 (如 lung): {stats['anatomical_only']}")
    print(f"  混合型 (如 left, lung): {stats['mixed']}")

    # TOP概念（仅真实疾病）
    print("\n[TOP 20 全局概念（仅真实疾病）]")
    print("-" * 100)
    print(f"{'序号':<4} {'概念键':<30} {'修饰词':<20} {'解剖概念':<20} {'频次':>8}")
    print("-" * 100)

    for i, (concept_key, count) in enumerate(filtered_global.most_common(20), 1):
        details = results['concept_details'][concept_key]
        modifiers_str = '; '.join(details['modifiers'])[:20] if details['modifiers'] else '-'
        anatomical_str = details['anatomical'][:20] if details['anatomical'] else '-'

        print(f"{i:<4} {concept_key:<30} {modifiers_str:<20} {anatomical_str:<20} {count:>8}")

    # support devices 概念
    if sd_concepts:
        print(f"\n[support devices 概念 TOP 15]")
        print("-" * 100)
        for i, (concept_key, count) in enumerate(sorted(sd_concepts.items(), key=lambda x: -x[1])[:15], 1):
            details = results['concept_details'][concept_key]
            modifiers_str = ', '.join(details['modifiers']) if details['modifiers'] else '-'
            anatomical_str = details['anatomical'] if details['anatomical'] else '-'
            print(f"  {i:2d}. ({modifiers_str:<20}, {anatomical_str:<25}) → {count:5d} | 示例: {details['examples'][0][:40] if details['examples'] else 'N/A'}")

    # no finding 概念
    if nf_concepts:
        print(f"\n[no finding 概念 TOP 10]")
        print("-" * 100)
        for i, (concept_key, count) in enumerate(sorted(nf_concepts.items(), key=lambda x: -x[1])[:10], 1):
            details = results['concept_details'][concept_key]
            modifiers_str = ', '.join(details['modifiers']) if details['modifiers'] else '-'
            anatomical_str = details['anatomical'] if details['anatomical'] else '-'
            print(f"  {i:2d}. ({modifiers_str:<20}, {anatomical_str:<25}) → {count:5d}")

    # pleural effusion 的概念
    if 'pleural effusion' in results['disease_concepts']:
        print(f"\n[pleural effusion 的标准化概念 TOP 15]")
        print("-" * 100)
        pe_concepts = results['disease_concepts']['pleural effusion']

        for i, (concept_key, count) in enumerate(sorted(pe_concepts.items(), key=lambda x: -x[1])[:15], 1):
            details = results['concept_details'][concept_key]
            modifiers_str = ', '.join(details['modifiers']) if details['modifiers'] else '-'
            anatomical_str = details['anatomical'] if details['anatomical'] else '-'
            print(f"  {i:2d}. ({modifiers_str:<15}, {anatomical_str:<20}) → {count:5d} 次 | 示例: {details['examples'][0] if details['examples'] else 'N/A'}")


if __name__ == "__main__":
    input_csv = "disease_phrase_counts.csv"
    mapping_json = "synonym_mapping.json"
    output_dir = Path(".")

    # 检查输入文件
    if not Path(input_csv).exists():
        print(f"错误: 文件不存在 - {input_csv}")
        print("请先运行 extract_disease_phrase_counts.py")
        exit(1)

    if not Path(mapping_json).exists():
        print(f"错误: 文件不存在 - {mapping_json}")
        print("请先运行 merge_synonyms_in_concept_pool.py")
        exit(1)

    # 1. 加载数据
    print("加载原始短语数据...")
    disease_phrases = load_original_phrases(input_csv)
    print(f"  加载了 {len(disease_phrases)} 种疾病")

    print("\n加载同义词映射...")
    modifier_mapping, anatomical_mapping = load_synonym_mapping(mapping_json)
    print(f"  修饰词映射: {len(modifier_mapping)} 条")
    print(f"  解剖概念映射: {len(anatomical_mapping)} 条")

    # 2. 创建拆解器
    print("\n初始化短语拆解器...")
    decomposer = PhraseDecomposer()

    # 3. 标准化并计数
    print("\n标准化短语并重新计数...")
    results = normalize_and_count(
        disease_phrases,
        decomposer,
        modifier_mapping,
        anatomical_mapping
    )

    # 4. 保存结果
    print("\n保存结果...")
    save_results(results, output_dir)

    # 5. 打印摘要
    print_summary(results)

    print("\n完成!")
