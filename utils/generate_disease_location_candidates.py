"""
生成疾病位置候选集合

要求:
1. 只处理 schema 中 enable_location=true 的 disease
2. 只统计 has_location_supervision=true 的样本
3. 按 disease 聚合 location_concepts
4. 用"覆盖率优先"选 Top-K (<= location_budget)
5. 修饰词单独选 (通常 5 个以内)
"""

import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Set


def load_disease_schema(schema_path: str) -> Dict:
    """加载疾病 schema"""
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    return schema


def load_concept_pool(pool_path: str) -> Dict:
    """加载概念池"""
    with open(pool_path, 'r', encoding='utf-8') as f:
        pool = json.load(f)
    return pool


def filter_enabled_diseases(schema: Dict) -> Dict[str, int]:
    """获取 enable_location=true 的疾病及其 location_budget"""
    enabled_diseases = {}
    for disease_name, disease_info in schema['diseases'].items():
        if disease_info.get('enable_location', False):
            budget = disease_info.get('location_budget', 30)
            enabled_diseases[disease_name] = budget
    return enabled_diseases


def collect_location_statistics(
    data_path: str,
    enabled_diseases: Set[str]
) -> Dict[str, Dict[str, Counter]]:
    """
    收集位置统计

    返回: {
        'disease_name': {
            'concepts': Counter,  # location_concepts 计数
            'modifiers': Counter  # location_modifiers 计数
        }
    }
    """
    stats = defaultdict(lambda: {'concepts': Counter(), 'modifiers': Counter()})

    total_samples = 0
    supervised_samples = 0

    print(f"开始处理数据集: {data_path}")

    with open(data_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            # 跳过空行
            if not line.strip():
                continue

            total_samples += 1

            try:
                sample = json.loads(line)

                # 处理 positive_findings
                for finding in sample.get('positive_findings', []):
                    disease_name = finding.get('disease_name', '')

                    # 只统计启用的疾病
                    if disease_name not in enabled_diseases:
                        continue

                    # 只统计有监督信号的样本
                    if not finding.get('has_location_supervision', False):
                        continue

                    supervised_samples += 1

                    # 统计 location_concepts
                    for concept in finding.get('location_concepts', []):
                        if concept:  # 忽略空字符串
                            stats[disease_name]['concepts'][concept] += 1

                    # 统计 location_modifiers
                    for modifier in finding.get('location_modifiers', []):
                        if modifier:
                            stats[disease_name]['modifiers'][modifier] += 1

                # 进度显示
                if line_num % 10000 == 0:
                    print(f"  已处理 {line_num} 行...")

            except json.JSONDecodeError as e:
                print(f"警告: 行 {line_num} JSON 解析失败: {e}")
                continue
            except Exception as e:
                print(f"警告: 行 {line_num} 处理失败: {e}")
                continue

    print(f"\n数据集处理完成:")
    print(f"  总样本数: {total_samples}")
    print(f"  有监督信号的 finding 数: {supervised_samples}")

    return dict(stats)


def select_top_concepts(
    concept_counter: Counter,
    location_budget: int,
    concept_pool: Dict
) -> List[str]:
    """
    选择 Top-K 概念

    策略: 覆盖率优先 - 选择频次最高的概念
    """
    # 按频次排序
    sorted_concepts = concept_counter.most_common()

    # 选择前 K 个（不超过 budget）
    top_k = min(location_budget, len(sorted_concepts))
    selected = [concept for concept, count in sorted_concepts[:top_k]]

    return selected


def select_top_modifiers(
    modifier_counter: Counter,
    max_modifiers: int = 5
) -> List[str]:
    """
    选择 Top-K 修饰词

    修饰词通常比较集中，5 个以内就够
    """
    # 按频次排序
    sorted_modifiers = modifier_counter.most_common()

    # 选择前 K 个（不超过 max_modifiers）
    top_k = min(max_modifiers, len(sorted_modifiers))
    selected = [modifier for modifier, count in sorted_modifiers[:top_k]]

    return selected


def generate_candidates(
    stats: Dict[str, Dict[str, Counter]],
    enabled_diseases: Dict[str, int],
    concept_pool: Dict
) -> Dict:
    """
    生成候选集合

    返回格式:
    {
        "disease_name": {
            "concept_candidates": [...],
            "modifier_candidates": [...],
            "version": "v1.0",
            "source": "stats_topk_coverage"
        }
    }
    """
    candidates = {}

    print("\n生成候选集合...")
    print("=" * 80)

    for disease_name, budget in sorted(enabled_diseases.items()):
        if disease_name not in stats:
            print(f"警告: {disease_name} 没有统计数据")
            # 创建空候选
            candidates[disease_name] = {
                "concept_candidates": [],
                "modifier_candidates": [],
                "version": "v1.0",
                "source": "stats_topk_coverage",
                "note": "No supervised data found"
            }
            continue

        disease_stats = stats[disease_name]

        # 选择概念候选
        concept_candidates = select_top_concepts(
            disease_stats['concepts'],
            budget,
            concept_pool
        )

        # 选择修饰词候选
        modifier_candidates = select_top_modifiers(disease_stats['modifiers'])

        candidates[disease_name] = {
            "concept_candidates": concept_candidates,
            "modifier_candidates": modifier_candidates,
            "version": "v1.0",
            "source": "stats_topk_coverage"
        }

        # 打印统计信息
        total_concept_count = sum(disease_stats['concepts'].values())
        unique_concepts = len(disease_stats['concepts'])

        print(f"\n{disease_name}:")
        print(f"  Budget: {budget}")
        print(f"  统计: {unique_concepts} 个唯一概念, 总计 {total_concept_count} 次出现")
        print(f"  选中概念数: {len(concept_candidates)}")
        if concept_candidates:
            print(f"  TOP 5 概念:")
            for i, concept in enumerate(concept_candidates[:5], 1):
                count = disease_stats['concepts'][concept]
                print(f"    {i}. {concept}: {count}")

        if modifier_candidates:
            print(f"  修饰词: {modifier_candidates}")
            print(f"    TOP 5 修饰词:")
            for i, modifier in enumerate(modifier_candidates[:5], 1):
                count = disease_stats['modifiers'][modifier]
                print(f"    {i}. {modifier}: {count}")

    return candidates


def save_candidates(candidates: Dict, output_path: str):
    """保存候选集合"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(candidates, f, indent=2, ensure_ascii=False)

    print(f"\n候选集合已保存到: {output_path}")


def print_summary(candidates: Dict, stats: Dict[str, Dict[str, Counter]]):
    """打印统计摘要"""
    print("\n" + "=" * 80)
    print("候选集合生成摘要")
    print("=" * 80)

    print(f"\n总疾病数: {len(candidates)}")

    # 统计概念数量
    total_concepts = sum(len(c['concept_candidates']) for c in candidates.values())
    diseases_with_concepts = sum(1 for c in candidates.values() if c['concept_candidates'])

    print(f"有概念候选的疾病: {diseases_with_concepts}")
    print(f"总概念候选数: {total_concepts}")
    print(f"平均每疾病: {total_concepts / max(diseases_with_concepts, 1):.1f}")

    # 统计修饰词数量
    total_modifiers = sum(len(c['modifier_candidates']) for c in candidates.values())
    diseases_with_modifiers = sum(1 for c in candidates.values() if c['modifier_candidates'])

    print(f"\n有修饰词候选的疾病: {diseases_with_modifiers}")
    print(f"总修饰词候选数: {total_modifiers}")

    # TOP 概念全局统计
    all_concepts = Counter()
    for disease_name, disease_stats in stats.items():
        all_concepts.update(disease_stats['concepts'])

    print(f"\n全局 TOP 20 概念:")
    print("-" * 60)
    for i, (concept, count) in enumerate(all_concepts.most_common(20), 1):
        print(f"  {i:2d}. {concept:<30} {count:>6}")

    # TOP 修饰词全局统计
    all_modifiers = Counter()
    for disease_name, disease_stats in stats.items():
        all_modifiers.update(disease_stats['modifiers'])

    print(f"\n全局 TOP 10 修饰词:")
    print("-" * 60)
    for i, (modifier, count) in enumerate(all_modifiers.most_common(10), 1):
        print(f"  {i:2d}. {modifier:<30} {count:>6}")


def main():
    # 文件路径
    schema_path = "disease_schema.json"
    data_path = "data/mimic-cxr-a/all_structured_reports_with_location_concepts.jsonl"
    concept_pool_path = "location_concept_pool_v4.json"
    output_path = "disease_location_candidates.json"

    # 检查文件存在
    if not Path(schema_path).exists():
        print(f"错误: 文件不存在 - {schema_path}")
        return

    if not Path(data_path).exists():
        print(f"错误: 文件不存在 - {data_path}")
        return

    if not Path(concept_pool_path).exists():
        print(f"错误: 文件不存在 - {concept_pool_path}")
        return

    # 1. 加载 schema
    print("加载疾病 schema...")
    schema = load_disease_schema(schema_path)

    # 2. 获取启用的疾病
    enabled_diseases = filter_enabled_diseases(schema)
    print(f"启用的疾病数: {len(enabled_diseases)}")
    for disease, budget in sorted(enabled_diseases.items()):
        print(f"  {disease}: budget={budget}")

    # 3. 加载概念池
    print(f"\n加载概念池...")
    concept_pool = load_concept_pool(concept_pool_path)
    print(f"概念池总数: {len(concept_pool)}")

    # 4. 收集统计
    stats = collect_location_statistics(data_path, set(enabled_diseases.keys()))

    # 5. 生成候选
    candidates = generate_candidates(stats, enabled_diseases, concept_pool)

    # 6. 保存
    save_candidates(candidates, output_path)

    # 7. 打印摘要
    print_summary(candidates, stats)

    print("\n完成!")


if __name__ == "__main__":
    main()
