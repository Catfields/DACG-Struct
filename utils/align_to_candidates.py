"""
将数据集对齐到候选集合

使用 disease_location_candidates.json 对 concepts 和 modifiers 进行过滤:
- concepts = [c for c in concepts if c in concept_candidates[disease]]
- modifiers = [m for m in modifiers if m in modifier_candidates[disease]]

保证训练时 label 一定落在候选集合维度内
"""

import json
from pathlib import Path
from typing import Dict, List, Set, Any


def load_candidates(candidates_path: str) -> Dict[str, Dict[str, List[str]]]:
    """加载候选集合"""
    with open(candidates_path, 'r', encoding='utf-8') as f:
        candidates = json.load(f)
    return candidates


def align_finding(
    finding: Dict[str, Any],
    candidates: Dict[str, Dict[str, List[str]]],
    disease_name: str
) -> Dict[str, Any]:
    """
    对齐单个 finding 到候选集合

    返回:
    {
        'disease_name': str,
        'probability': int,
        'severity': int,
        'location_raw': str,
        'location_concepts': List[str],  # 过滤后
        'location_modifiers': List[str],  # 过滤后
        'has_location_supervision': bool,
        'aligned_concepts': List[str],  # 候选集合中的概念
        'aligned_modifiers': List[str],  # 候选集合中的修饰词
        'filtered_concepts': List[str],  # 被过滤掉的概念
        'filtered_modifiers': List[str]  # 被过滤掉的修饰词
    }
    """
    # 获取该疾病的候选集合
    disease_candidates = candidates.get(disease_name, {})

    concept_candidates = set(disease_candidates.get('concept_candidates', []))
    modifier_candidates = set(disease_candidates.get('modifier_candidates', []))

    # 原始 concepts 和 modifiers
    original_concepts = finding.get('location_concepts', [])
    original_modifiers = finding.get('location_modifiers', [])

    # 过滤：只保留在候选集合中的
    aligned_concepts = [c for c in original_concepts if c in concept_candidates]
    aligned_modifiers = [m for m in original_modifiers if m in modifier_candidates]

    # 记录被过滤掉的部分（用于调试）
    filtered_concepts = [c for c in original_concepts if c not in concept_candidates]
    filtered_modifiers = [m for m in original_modifiers if m not in modifier_candidates]

    # 判断是否有位置监督（对齐后）
    has_supervision = bool(aligned_concepts or aligned_modifiers)

    return {
        'disease_name': finding.get('disease_name', ''),
        'probability': finding.get('probability', 0),
        'severity': finding.get('severity', 0),
        'location_raw': finding.get('location_raw', ''),
        'location_concepts': aligned_concepts,
        'location_modifiers': aligned_modifiers,
        'has_location_supervision': has_supervision,
        'aligned_concepts': aligned_concepts,
        'aligned_modifiers': aligned_modifiers,
        'filtered_concepts': filtered_concepts,
        'filtered_modifiers': filtered_modifiers
    }


def align_sample(
    sample: Dict[str, Any],
    candidates: Dict[str, Dict[str, List[str]]]
) -> Dict[str, Any]:
    """对齐单个样本"""
    aligned_sample = {
        'positive_findings': [],
        'negative_findings': sample.get('negative_findings', []),
        'extraction_note': sample.get('extraction_note', ''),
        'metadata': sample.get('metadata', {})
    }

    # 对齐 positive_findings
    for finding in sample.get('positive_findings', []):
        disease_name = finding.get('disease_name', '')

        # 如果该疾病没有候选集合，保持原样（但标记为无监督）
        if disease_name not in candidates:
            aligned_finding = {
                'disease_name': disease_name,
                'probability': finding.get('probability', 0),
                'severity': finding.get('severity', 0),
                'location_raw': finding.get('location_raw', ''),
                'location_concepts': [],
                'location_modifiers': [],
                'has_location_supervision': False,
                'aligned_concepts': [],
                'aligned_modifiers': [],
                'filtered_concepts': finding.get('location_concepts', []),
                'filtered_modifiers': finding.get('location_modifiers', []),
                'filter_reason': 'no_candidates'
            }
        else:
            aligned_finding = align_finding(finding, candidates, disease_name)

        aligned_sample['positive_findings'].append(aligned_finding)

    return aligned_sample


def align_dataset(
    input_path: str,
    output_path: str,
    candidates: Dict[str, Dict[str, List[str]]],
    limit: int = None
) -> Dict[str, int]:
    """对齐整个数据集"""

    stats = {
        'total_samples': 0,
        'total_findings': 0,
        'findings_with_supervision_before': 0,
        'findings_with_supervision_after': 0,
        'concepts_filtered': 0,  # 被过滤掉的概念总数
        'modifiers_filtered': 0,  # 被过滤掉的修饰词总数
        'findings_no_candidates': 0,  # 没有候选集合的 finding 数
        'concepts_aligned': 0,  # 对齐后的概念总数
        'modifiers_aligned': 0,  # 对齐后的修饰词总数
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

                # 统计对齐前
                for finding in sample.get('positive_findings', []):
                    stats['total_findings'] += 1
                    if finding.get('has_location_supervision', False):
                        stats['findings_with_supervision_before'] += 1

                # 对齐样本
                aligned_sample = align_sample(sample, candidates)

                # 统计对齐后
                for finding in aligned_sample['positive_findings']:
                    if finding.get('has_location_supervision', False):
                        stats['findings_with_supervision_after'] += 1
                    else:
                        if finding.get('filter_reason') == 'no_candidates':
                            stats['findings_no_candidates'] += 1

                    stats['concepts_filtered'] += len(finding.get('filtered_concepts', []))
                    stats['modifiers_filtered'] += len(finding.get('filtered_modifiers', []))
                    stats['concepts_aligned'] += len(finding.get('aligned_concepts', []))
                    stats['modifiers_aligned'] += len(finding.get('aligned_modifiers', []))

                # 写入
                f_out.write(json.dumps(aligned_sample, ensure_ascii=False) + '\n')

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
    print("候选集合对齐统计")
    print("=" * 80)

    print(f"\n样本统计:")
    print(f"  总样本数: {stats['total_samples']}")

    print(f"\nFinding 统计:")
    print(f"  总 finding 数: {stats['total_findings']}")
    print(f"  对齐前有监督: {stats['findings_with_supervision_before']} ({stats['findings_with_supervision_before']/max(stats['total_findings'],1)*100:.1f}%)")
    print(f"  对齐后有监督: {stats['findings_with_supervision_after']} ({stats['findings_with_supervision_after']/max(stats['total_findings'],1)*100:.1f}%)")
    print(f"  无候选集合: {stats['findings_no_candidates']}")

    print(f"\n过滤统计:")
    print(f"  被过滤的概念总数: {stats['concepts_filtered']}")
    print(f"  被过滤的修饰词总数: {stats['modifiers_filtered']}")
    print(f"  对齐后的概念总数: {stats['concepts_aligned']}")
    print(f"  对齐后的修饰词总数: {stats['modifiers_aligned']}")

    if stats['findings_with_supervision_before'] > 0:
        supervision_loss = stats['findings_with_supervision_before'] - stats['findings_with_supervision_after']
        print(f"  监督信号丢失: {supervision_loss} ({supervision_loss/stats['findings_with_supervision_before']*100:.1f}%)")


def print_candidates_summary(candidates: Dict[str, Dict[str, List[str]]]):
    """打印候选集合摘要"""
    print("\n" + "=" * 80)
    print("候选集合摘要")
    print("=" * 80)

    print(f"\n总疾病数: {len(candidates)}")

    total_concepts = sum(len(c.get('concept_candidates', [])) for c in candidates.values())
    total_modifiers = sum(len(c.get('modifier_candidates', [])) for c in candidates.values())

    print(f"总概念候选数: {total_concepts}")
    print(f"总修饰词候选数: {total_modifiers}")
    print(f"平均每疾病概念数: {total_concepts/len(candidates):.1f}")
    print(f"平均每疾病修饰词数: {total_modifiers/len(candidates):.1f}")

    print(f"\n各疾病的候选数:")
    print(f"{'疾病名':<40} {'概念候选':<10} {'修饰词候选':<10}")
    print("-" * 60)
    for disease, info in sorted(candidates.items()):
        concepts = len(info.get('concept_candidates', []))
        modifiers = len(info.get('modifier_candidates', []))
        print(f"{disease:<40} {concepts:<10} {modifiers:<10}")


def test_alignment(candidates: Dict[str, Dict[str, List[str]]]):
    """测试对齐功能"""
    print("\n" + "=" * 80)
    print("测试对齐功能")
    print("=" * 80)

    test_findings = [
        {
            'disease_name': 'pleural_effusion',
            'location_raw': 'bilateral pleural space',
            'location_concepts': ['pleural_space', 'uncommon_concept'],
            'location_modifiers': ['bilateral', 'uncommon_modifier']
        },
        {
            'disease_name': 'consolidation',
            'location_raw': 'right lower lobe',
            'location_concepts': ['lobe', 'lingula'],
            'location_modifiers': ['right', 'lower', 'focal']
        },
        {
            'disease_name': 'unknown_disease',
            'location_raw': 'some location',
            'location_concepts': ['lung'],
            'location_modifiers': ['left']
        }
    ]

    for finding in test_findings:
        print(f"\n原始 finding:")
        print(f"  疾病: {finding['disease_name']}")
        print(f"  位置: {finding['location_raw']}")
        print(f"  概念: {finding['location_concepts']}")
        print(f"  修饰词: {finding['location_modifiers']}")

        aligned = align_finding(finding, candidates, finding['disease_name'])

        print(f"\n对齐后:")
        print(f"  概念: {aligned['location_concepts']}")
        print(f"  修饰词: {aligned['location_modifiers']}")
        print(f"  被过滤的概念: {aligned['filtered_concepts']}")
        print(f"  被过滤的修饰词: {aligned['filtered_modifiers']}")
        print(f"  有监督: {aligned['has_location_supervision']}")


def main():
    # 文件路径
    candidates_path = "disease_location_candidates.json"
    input_path = "data/mimic-cxr-a/all_structured_reports_normalized_v2.jsonl"
    output_path = "data/mimic-cxr-a/all_structured_reports_aligned.jsonl"

    # 检查文件
    if not Path(candidates_path).exists():
        print(f"错误: 候选集合文件不存在 - {candidates_path}")
        return

    if not Path(input_path).exists():
        print(f"错误: 输入文件不存在 - {input_path}")
        return

    # 加载候选集合
    print("加载候选集合...")
    candidates = load_candidates(candidates_path)
    print(f"  疾病数: {len(candidates)}")

    # 打印候选集合摘要
    print_candidates_summary(candidates)

    # 测试对齐功能
    test_alignment(candidates)

    # 对齐数据集
    print(f"\n开始对齐数据集...")
    print(f"  输入: {input_path}")
    print(f"  输出: {output_path}")

    # 创建输出目录
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 执行对齐
    stats = align_dataset(input_path, output_path, candidates, limit=None)

    # 打印统计
    print_statistics(stats)

    print(f"\n完成! 对齐后的数据已保存到: {output_path}")


if __name__ == "__main__":
    main()
