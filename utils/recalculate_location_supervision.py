"""
重新计算 has_location_supervision

规则:
1. 若 enable_location=false → has_location_supervision=false
2. 若 enable_location=true:
   - concepts 非空 → true
   - concepts 为空但 modifiers 非空 → false (单独修饰词不算有效监督)
"""

import json
from pathlib import Path
from typing import Dict, List, Set, Any


def load_disease_schema(schema_path: str) -> Dict:
    """加载疾病 schema"""
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    return schema


def get_enabled_diseases(schema: Dict) -> Set[str]:
    """获取 enable_location=true 的疾病集合"""
    enabled = set()
    for disease_name, disease_info in schema['diseases'].items():
        if disease_info.get('enable_location', False):
            enabled.add(disease_name)
    return enabled


def recalculate_finding_supervision(
    finding: Dict[str, Any],
    enabled_diseases: Set[str]
) -> Dict[str, Any]:
    """
    重新计算单个 finding 的 has_location_supervision

    返回更新后的 finding
    """
    disease_name = finding.get('disease_name', '')
    concepts = finding.get('location_concepts', [])
    modifiers = finding.get('location_modifiers', [])

    # 规则1: enable_location=false → false
    if disease_name not in enabled_diseases:
        has_supervision = False
    # 规则2: enable_location=true
    else:
        # concepts 非空 → true
        if concepts:
            has_supervision = True
        # concepts 为空但 modifiers 非空 → false
        # concepts 为空且 modifiers 为空 → false
        else:
            has_supervision = False

    # 更新 finding
    finding['has_location_supervision'] = has_supervision

    return finding


def recalculate_sample_supervision(
    sample: Dict[str, Any],
    enabled_diseases: Set[str]
) -> Dict[str, Any]:
    """重新计算样本中所有 findings 的监督信号"""
    for finding in sample.get('positive_findings', []):
        recalculate_finding_supervision(finding, enabled_diseases)

    return sample


def recalculate_dataset_supervision(
    input_path: str,
    output_path: str,
    enabled_diseases: Set[str],
    limit: int = None
) -> Dict[str, int]:
    """重新计算整个数据集的监督信号"""

    stats = {
        'total_samples': 0,
        'total_findings': 0,
        'supervision_before': 0,
        'supervision_after': 0,
        'supervision_gained': 0,  # 从 false 变为 true
        'supervision_lost': 0,  # 从 true 变为 false
        'findings_disabled': 0,  # enable_location=false 的 finding 数
        'findings_with_concepts': 0,  # concepts 非空的 finding 数
        'findings_modifiers_only': 0,  # 只有 modifiers 的 finding 数
        'findings_no_location': 0,  # 完全没有位置信息的 finding 数
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

                # 重新计算监督信号
                for finding in sample.get('positive_findings', []):
                    stats['total_findings'] += 1

                    disease_name = finding.get('disease_name', '')
                    concepts = finding.get('location_concepts', [])
                    modifiers = finding.get('location_modifiers', [])

                    # 记录旧值
                    supervision_before = finding.get('has_location_supervision', False)
                    stats['supervision_before'] += supervision_before

                    # 统计位置信息情况
                    if disease_name not in enabled_diseases:
                        stats['findings_disabled'] += 1
                    elif concepts:
                        stats['findings_with_concepts'] += 1
                    elif modifiers:
                        stats['findings_modifiers_only'] += 1
                    else:
                        stats['findings_no_location'] += 1

                    # 重新计算
                    recalculate_finding_supervision(finding, enabled_diseases)

                    # 记录新值
                    supervision_after = finding.get('has_location_supervision', False)
                    stats['supervision_after'] += supervision_after

                    # 统计变化
                    if supervision_before and not supervision_after:
                        stats['supervision_lost'] += 1
                    elif not supervision_before and supervision_after:
                        stats['supervision_gained'] += 1

                # 写入
                f_out.write(json.dumps(sample, ensure_ascii=False) + '\n')

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


def print_statistics(stats: Dict[str, int], enabled_diseases: Set[str]):
    """打印统计信息"""
    print("\n" + "=" * 80)
    print("重新计算监督信号统计")
    print("=" * 80)

    print(f"\n启用位置建模的疾病: {len(enabled_diseases)}")
    print(f"  {', '.join(sorted(enabled_diseases))}")

    print(f"\n样本统计:")
    print(f"  总样本数: {stats['total_samples']}")

    print(f"\nFinding 统计:")
    print(f"  总 finding 数: {stats['total_findings']}")
    print(f"  重新计算前有监督: {stats['supervision_before']} ({stats['supervision_before']/max(stats['total_findings'],1)*100:.1f}%)")
    print(f"  重新计算后有监督: {stats['supervision_after']} ({stats['supervision_after']/max(stats['total_findings'],1)*100:.1f}%)")

    print(f"\n监督信号变化:")
    print(f"  获得监督: {stats['supervision_gained']}")
    print(f"  丢失监督: {stats['supervision_lost']}")
    net_change = stats['supervision_after'] - stats['supervision_before']
    print(f"  净变化: {net_change:+d}")

    print(f"\nFinding 分类:")
    print(f"  enable_location=true 且有 concepts: {stats['findings_with_concepts']}")
    print(f"  enable_location=true 但只有 modifiers: {stats['findings_modifiers_only']}")
    print(f"  enable_location=true 且无位置信息: {stats['findings_no_location']}")
    print(f"  enable_location=false: {stats['findings_disabled']}")

    # 验证
    total_classified = (stats['findings_with_concepts'] +
                       stats['findings_modifiers_only'] +
                       stats['findings_no_location'] +
                       stats['findings_disabled'])
    print(f"\n验证分类总和: {total_classified} (总计: {stats['total_findings']})")


def analyze_by_disease(
    input_path: str,
    enabled_diseases: Set[str],
    limit: int = None
):
    """按疾病分析监督信号变化"""
    from collections import defaultdict

    disease_stats = defaultdict(lambda: {
        'total': 0,
        'enabled': False,
        'supervision_before': 0,
        'supervision_after': 0,
        'with_concepts': 0,
        'modifiers_only': 0,
        'no_location': 0,
    })

    with open(input_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f):
            if limit and line_num >= limit:
                break

            if not line.strip():
                continue

            try:
                sample = json.loads(line)

                for finding in sample.get('positive_findings', []):
                    disease = finding.get('disease_name', '')
                    disease_stats[disease]['total'] += 1
                    disease_stats[disease]['enabled'] = disease in enabled_diseases

                    supervision_before = finding.get('has_location_supervision', False)
                    disease_stats[disease]['supervision_before'] += supervision_before

                    concepts = finding.get('location_concepts', [])
                    modifiers = finding.get('location_modifiers', [])

                    if concepts:
                        disease_stats[disease]['with_concepts'] += 1
                    elif modifiers:
                        disease_stats[disease]['modifiers_only'] += 1
                    else:
                        disease_stats[disease]['no_location'] += 1

                    # 重新计算
                    if disease not in enabled_diseases:
                        supervision_after = False
                    else:
                        supervision_after = bool(concepts)

                    disease_stats[disease]['supervision_after'] += supervision_after

            except Exception:
                continue

    # 打印结果
    print("\n" + "=" * 80)
    print("按疾病分类的监督信号变化")
    print("=" * 80)
    print(f"{'疾病名':<40} {'启用':>6} {'总数':>6} {'监督前':>6} {'监督后':>6} {'有概念':>6} {'仅修饰':>6} {'无位置':>6}")
    print("-" * 90)

    for disease in sorted(disease_stats.keys()):
        stats = disease_stats[disease]
        print(f"{disease:<40} {'是' if stats['enabled'] else '否':>6} {stats['total']:>6} {stats['supervision_before']:>6} {stats['supervision_after']:>6} {stats['with_concepts']:>6} {stats['modifiers_only']:>6} {stats['no_location']:>6}")


def main():
    # 文件路径
    schema_path = "disease_schema.json"
    input_path = "data/mimic-cxr-a/all_structured_reports_aligned.jsonl"
    output_path = "data/mimic-cxr-a/all_structured_reports_final.jsonl"

    # 检查文件
    if not Path(schema_path).exists():
        print(f"错误: Schema 文件不存在 - {schema_path}")
        return

    if not Path(input_path).exists():
        print(f"错误: 输入文件不存在 - {input_path}")
        return

    # 加载 schema
    print("加载疾病 schema...")
    schema = load_disease_schema(schema_path)

    # 获取启用位置建模的疾病
    enabled_diseases = get_enabled_diseases(schema)
    print(f"启用位置建模的疾病数: {len(enabled_diseases)}")

    # 重新计算监督信号
    print(f"\n开始重新计算监督信号...")
    print(f"  输入: {input_path}")
    print(f"  输出: {output_path}")

    # 创建输出目录
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 执行重新计算
    stats = recalculate_dataset_supervision(input_path, output_path, enabled_diseases, limit=None)

    # 打印统计
    print_statistics(stats, enabled_diseases)

    # 按疾病分析
    analyze_by_disease(input_path, enabled_diseases, limit=None)

    print(f"\n完成! 重新计算后的数据已保存到: {output_path}")


if __name__ == "__main__":
    main()
