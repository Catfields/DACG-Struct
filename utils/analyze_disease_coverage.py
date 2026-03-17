import json
from collections import defaultdict, Counter

def analyze_disease_coverage(jsonl_file):
    """
    统计阳性疾病和阴性疾病的覆盖率
    """

    # 统计数据
    positive_disease_coverage = defaultdict(set)  # 阳性疾病 -> 报告ID集合
    negative_disease_coverage = defaultdict(set)  # 阴性疾病 -> 报告ID集合
    all_disease_coverage = defaultdict(set)       # 所有疾病 -> 报告ID集合

    total_reports = 0
    positive_reports = 0  # 有阳性发现的报告数
    negative_reports = 0  # 有阴性发现的报告数
    both_findings_reports = 0  # 同时有阳性和阴性发现的报告数

    print("正在读取和分析数据...")

    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if line_num % 5000 == 0:
                print(f"处理进度: {line_num} 行")

            line = line.strip()
            if not line:
                continue

            try:
                if '|' in line:
                    pipe_index = line.find('|')
                    line = line[pipe_index + 1:].lstrip()

                data = json.loads(line)

                if 'metadata' not in data:
                    continue

                report_id = data['metadata']['id']
                total_reports += 1

                # 获取阳性和阴性发现
                positive_findings = data.get('positive_findings', [])
                negative_findings = data.get('negative_findings', [])

                has_positive = len(positive_findings) > 0
                has_negative = len(negative_findings) > 0

                if has_positive:
                    positive_reports += 1
                if has_negative:
                    negative_reports += 1
                if has_positive and has_negative:
                    both_findings_reports += 1

                # 处理阳性发现
                for finding in positive_findings:
                    disease_name = finding.get('disease_name', '')

                    # 跳过"no finding"这种非实际疾病
                    if disease_name.lower() in ['no finding', 'no findings']:
                        continue

                    positive_disease_coverage[disease_name].add(report_id)
                    all_disease_coverage[disease_name].add(report_id)

                # 处理阴性发现
                for finding in negative_findings:
                    # negative_findings是字符串列表，不是字典列表
                    if isinstance(finding, str):
                        disease_name = finding.strip()
                    else:
                        disease_name = finding.get('disease_name', '') if isinstance(finding, dict) else ''

                    # 跳过"no finding"这种非实际疾病
                    if disease_name.lower() in ['no finding', 'no findings'] or not disease_name:
                        continue

                    negative_disease_coverage[disease_name].add(report_id)
                    all_disease_coverage[disease_name].add(report_id)

            except json.JSONDecodeError:
                continue
            except Exception:
                continue

    print(f"\n数据统计概览:")
    print(f"总报告数: {total_reports}")
    print(f"有阳性发现的报告数: {positive_reports}")
    print(f"有阴性发现的报告数: {negative_reports}")
    print(f"同时有阳性和阴性发现的报告数: {both_findings_reports}")

    # 计算覆盖率并排序
    def calculate_disease_stats(disease_coverage, total_reports, disease_type):
        stats = []
        for disease, report_ids in disease_coverage.items():
            coverage_count = len(report_ids)
            coverage_rate = coverage_count / total_reports * 100 if total_reports > 0 else 0
            stats.append((disease, coverage_count, coverage_rate))

        stats.sort(key=lambda x: x[1], reverse=True)
        return stats

    # 计算各种统计
    positive_stats = calculate_disease_stats(positive_disease_coverage, total_reports, "阳性")
    negative_stats = calculate_disease_stats(negative_disease_coverage, total_reports, "阴性")
    all_stats = calculate_disease_stats(all_disease_coverage, total_reports, "全部")

    return {
        'total_reports': total_reports,
        'positive_reports': positive_reports,
        'negative_reports': negative_reports,
        'both_findings_reports': both_findings_reports,
        'positive_stats': positive_stats,
        'negative_stats': negative_stats,
        'all_stats': all_stats
    }

def print_coverage_report(stats_dict):
    """
    打印覆盖率报告
    """

    print("\n" + "="*80)
    print("疾病覆盖率统计报告")
    print("="*80)

    # 基本统计信息
    print(f"\n基本统计:")
    print(f"  总报告数: {stats_dict['total_reports']:,}")
    print(f"  有阳性发现的报告: {stats_dict['positive_reports']:,} ({stats_dict['positive_reports']/stats_dict['total_reports']*100:.2f}%)")
    print(f"  有阴性发现的报告: {stats_dict['negative_reports']:,} ({stats_dict['negative_reports']/stats_dict['total_reports']*100:.2f}%)")
    print(f"  同时有阳性和阴性发现的报告: {stats_dict['both_findings_reports']:,} ({stats_dict['both_findings_reports']/stats_dict['total_reports']*100:.2f}%)")

    # 阳性疾病统计
    print(f"\n阳性疾病统计 (共 {len(stats_dict['positive_stats'])} 种):")
    print("-" * 60)
    for i, (disease, count, rate) in enumerate(stats_dict['positive_stats'][:20], 1):
        print(f"  {i:2d}. {disease:<30} {count:>6,} 次 ({rate:>5.2f}%)")

    if len(stats_dict['positive_stats']) > 20:
        print(f"  ... 还有 {len(stats_dict['positive_stats']) - 20} 种疾病")

    # 阴性疾病统计
    print(f"\n阴性疾病统计 (共 {len(stats_dict['negative_stats'])} 种):")
    print("-" * 60)
    for i, (disease, count, rate) in enumerate(stats_dict['negative_stats'][:20], 1):
        print(f"  {i:2d}. {disease:<30} {count:>6,} 次 ({rate:>5.2f}%)")

    if len(stats_dict['negative_stats']) > 20:
        print(f"  ... 还有 {len(stats_dict['negative_stats']) - 20} 种疾病")

    # 所有疾病统计
    print(f"\n所有疾病统计 (共 {len(stats_dict['all_stats'])} 种):")
    print("-" * 60)
    for i, (disease, count, rate) in enumerate(stats_dict['all_stats'][:20], 1):
        print(f"  {i:2d}. {disease:<30} {count:>6,} 次 ({rate:>5.2f}%)")

    if len(stats_dict['all_stats']) > 20:
        print(f"  ... 还有 {len(stats_dict['all_stats']) - 20} 种疾病")

    print("="*80)

def export_coverage_report(stats_dict, output_file):
    """
    导出覆盖率报告到文件
    """

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# MIMIC-CXR-A 疾病覆盖率统计报告\n\n")

        f.write("## 基本统计信息\n\n")
        f.write(f"- **总报告数**: {stats_dict['total_reports']:,}\n")
        f.write(f"- **有阳性发现的报告**: {stats_dict['positive_reports']:,} ({stats_dict['positive_reports']/stats_dict['total_reports']*100:.2f}%)\n")
        f.write(f"- **有阴性发现的报告**: {stats_dict['negative_reports']:,} ({stats_dict['negative_reports']/stats_dict['total_reports']*100:.2f}%)\n")
        f.write(f"- **同时有阳性和阴性发现的报告**: {stats_dict['both_findings_reports']:,} ({stats_dict['both_findings_reports']/stats_dict['total_reports']*100:.2f}%)\n\n")

        f.write(f"## 阳性疾病统计 (共 {len(stats_dict['positive_stats'])} 种)\n\n")
        f.write("| 排名 | 疾病名称 | 出现次数 | 覆盖率 |\n")
        f.write("|------|----------|----------|--------|\n")
        for i, (disease, count, rate) in enumerate(stats_dict['positive_stats'], 1):
            f.write(f"| {i} | {disease} | {count:,} | {rate:.2f}% |\n")

        f.write(f"\n## 阴性疾病统计 (共 {len(stats_dict['negative_stats'])} 种)\n\n")
        f.write("| 排名 | 疾病名称 | 出现次数 | 覆盖率 |\n")
        f.write("|------|----------|----------|--------|\n")
        for i, (disease, count, rate) in enumerate(stats_dict['negative_stats'], 1):
            f.write(f"| {i} | {disease} | {count:,} | {rate:.2f}% |\n")

        f.write(f"\n## 所有疾病统计 (共 {len(stats_dict['all_stats'])} 种)\n\n")
        f.write("| 排名 | 疾病名称 | 出现次数 | 覆盖率 |\n")
        f.write("|------|----------|----------|--------|\n")
        for i, (disease, count, rate) in enumerate(stats_dict['all_stats'], 1):
            f.write(f"| {i} | {disease} | {count:,} | {rate:.2f}% |\n")

    print(f"覆盖率报告已导出到: {output_file}")

def main():
    jsonl_file = "/home/y530/handsome/DACG/data/mimic-cxr-a/all_structured_reports_normalized.jsonl"
    output_file = "disease_coverage_report.md"

    print("开始分析疾病覆盖率...")

    # 分析疾病覆盖率
    stats_dict = analyze_disease_coverage(jsonl_file)

    # 打印报告
    print_coverage_report(stats_dict)

    # 导出到文件
    export_coverage_report(stats_dict, output_file)

    print(f"\n分析完成!")

if __name__ == "__main__":
    main()