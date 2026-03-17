"""
清理最终数据集，保留必要的 location 字段

保留字段:
- location_raw: 原始位置文本
- location_concepts: 对齐后的概念列表
- location_modifiers: 对齐后的修饰词列表
- has_location_supervision: 是否有位置监督

删除字段:
- aligned_concepts, aligned_modifiers
- filtered_concepts, filtered_modifiers
- filter_reason
"""

import json
from pathlib import Path
from typing import Dict, List, Any


def clean_finding(finding: Dict[str, Any]) -> Dict[str, Any]:
    """
    清理单个 finding，只保留必要的 location 字段

    保留:
    - disease_name
    - probability
    - severity
    - location_raw
    - location_concepts (对齐后)
    - location_modifiers (对齐后)
    - has_location_supervision

    删除:
    - aligned_concepts, aligned_modifiers
    - filtered_concepts, filtered_modifiers
    - filter_reason
    """
    # 创建干净的 finding
    clean_finding = {
        'disease_name': finding.get('disease_name', ''),
        'probability': finding.get('probability', 0),
        'severity': finding.get('severity', 0),
        'location_raw': finding.get('location_raw', ''),
        'location_concepts': finding.get('location_concepts', []),
        'location_modifiers': finding.get('location_modifiers', []),
        'has_location_supervision': finding.get('has_location_supervision', False)
    }

    return clean_finding


def clean_sample(sample: Dict[str, Any]) -> Dict[str, Any]:
    """清理单个样本"""
    clean_sample = {
        'positive_findings': [],
        'negative_findings': sample.get('negative_findings', []),
        'extraction_note': sample.get('extraction_note', ''),
        'metadata': sample.get('metadata', {})
    }

    # 清理每个 finding
    for finding in sample.get('positive_findings', []):
        clean_finding_dict = clean_finding(finding)
        clean_sample['positive_findings'].append(clean_finding_dict)

    return clean_sample


def clean_dataset(
    input_path: str,
    output_path: str,
    limit: int = None
) -> Dict[str, int]:
    """清理整个数据集"""

    stats = {
        'total_samples': 0,
        'total_findings': 0,
        'findings_with_supervision': 0,
        'findings_with_concepts': 0,
        'findings_with_modifiers': 0,
        'total_concepts': 0,
        'total_modifiers': 0,
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

                # 清理样本
                cleaned_sample = clean_sample(sample)

                # 统计
                for finding in cleaned_sample['positive_findings']:
                    stats['total_findings'] += 1

                    if finding.get('has_location_supervision', False):
                        stats['findings_with_supervision'] += 1

                    concepts = finding.get('location_concepts', [])
                    modifiers = finding.get('location_modifiers', [])

                    if concepts:
                        stats['findings_with_concepts'] += 1
                    if modifiers:
                        stats['findings_with_modifiers'] += 1

                    stats['total_concepts'] += len(concepts)
                    stats['total_modifiers'] += len(modifiers)

                # 写入
                f_out.write(json.dumps(cleaned_sample, ensure_ascii=False) + '\n')

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
    print("清理后数据集统计")
    print("=" * 80)

    print(f"\n样本统计:")
    print(f"  总样本数: {stats['total_samples']}")

    print(f"\nFinding 统计:")
    print(f"  总 finding 数: {stats['total_findings']}")
    print(f"  有位置监督: {stats['findings_with_supervision']} ({stats['findings_with_supervision']/max(stats['total_findings'],1)*100:.1f}%)")
    print(f"  有概念: {stats['findings_with_concepts']} ({stats['findings_with_concepts']/max(stats['total_findings'],1)*100:.1f}%)")
    print(f"  有修饰词: {stats['findings_with_modifiers']} ({stats['findings_with_modifiers']/max(stats['total_findings'],1)*100:.1f}%)")

    print(f"\nLocation 元素统计:")
    print(f"  总概念数: {stats['total_concepts']}")
    print(f"  总修饰词数: {stats['total_modifiers']}")

    if stats['findings_with_supervision'] > 0:
        print(f"  平均每 finding 概念数: {stats['total_concepts']/stats['findings_with_supervision']:.2f}")
        print(f"  平均每 finding 修饰词数: {stats['total_modifiers']/stats['findings_with_supervision']:.2f}")


def show_cleaned_sample_example(input_path: str, num_examples: int = 3):
    """展示清理后的样本示例"""
    print("\n" + "=" * 80)
    print("清理后的样本示例")
    print("=" * 80)

    count = 0
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            if count >= num_examples:
                break

            try:
                sample = json.loads(line)

                print(f"\n--- 样本 {count + 1} ---")
                print(f"Metadata: {sample.get('metadata', {}).get('id', 'N/A')}")
                print(f"\nPositive Findings:")

                for i, finding in enumerate(sample.get('positive_findings', [])[:3], 1):
                    print(f"\n  Finding {i}:")
                    print(f"    疾病: {finding.get('disease_name', 'N/A')}")
                    print(f"    概率: {finding.get('probability', 0)}")
                    print(f"    严重程度: {finding.get('severity', 0)}")
                    print(f"    原始位置: {finding.get('location_raw', 'N/A')}")
                    print(f"    概念: {finding.get('location_concepts', [])}")
                    print(f"    修饰词: {finding.get('location_modifiers', [])}")
                    print(f"    有监督: {finding.get('has_location_supervision', False)}")

                negative_findings = sample.get('negative_findings', [])
                if negative_findings:
                    print(f"\n  Negative Findings: {negative_findings[:5]}")

                count += 1

            except Exception as e:
                continue


def main():
    # 文件路径
    input_path = "data/mimic-cxr-a/all_structured_reports_final.jsonl"
    output_path = "data/mimic-cxr-a/all_structured_reports_train.jsonl"

    # 检查文件
    if not Path(input_path).exists():
        print(f"错误: 输入文件不存在 - {input_path}")
        return

    # 清理数据集
    print(f"开始清理数据集...")
    print(f"  输入: {input_path}")
    print(f"  输出: {output_path}")
    print(f"\n保留字段:")
    print(f"  - location_raw")
    print(f"  - location_concepts")
    print(f"  - location_modifiers")
    print(f"  - has_location_supervision")
    print(f"\n删除字段:")
    print(f"  - aligned_concepts, aligned_modifiers")
    print(f"  - filtered_concepts, filtered_modifiers")
    print(f"  - filter_reason")

    # 创建输出目录
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 执行清理
    stats = clean_dataset(input_path, output_path, limit=None)

    # 打印统计
    print_statistics(stats)

    # 展示示例
    show_cleaned_sample_example(output_path, num_examples=2)

    print(f"\n完成! 清理后的数据已保存到: {output_path}")


if __name__ == "__main__":
    main()
