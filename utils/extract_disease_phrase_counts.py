"""
提取疾病（阳性）下的解剖位置短语及其频次
生成CSV格式: disease, phrase, count
"""

import json
import csv
from collections import defaultdict
from pathlib import Path


def extract_disease_phrases(jsonl_path, output_csv):
    """
    从结构化报告中提取疾病与解剖位置短语的配对频次

    Args:
        jsonl_path: 输入的jsonl文件路径
        output_csv: 输出的csv文件路径
    """
    # 使用嵌套字典统计: disease -> (phrase -> count)
    disease_phrase_counts = defaultdict(lambda: defaultdict(int))

    total_records = 0
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            # 跳过空行
            if not line.strip():
                continue

            # 每行格式: "序号|JSON内容"
            if '|' in line:
                _, json_content = line.split('|', 1)
            else:
                json_content = line

            try:
                data = json.loads(json_content)
                total_records += 1

                # 处理阳性发现
                positive_findings = data.get('positive_findings', [])
                for finding in positive_findings:
                    disease_name = finding.get('disease_name', '')
                    anatomical_location = finding.get('anatomical_location', '')

                    # 处理None值
                    if disease_name is None:
                        disease_name = ''
                    if anatomical_location is None:
                        anatomical_location = ''

                    disease_name = disease_name.strip()
                    anatomical_location = anatomical_location.strip()

                    if disease_name and anatomical_location:
                        disease_phrase_counts[disease_name][anatomical_location] += 1

            except json.JSONDecodeError as e:
                print(f"警告: 解析JSON失败: {e}")
                continue

    # 写入CSV文件
    with open(output_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['disease', 'phrase', 'count'])

        for disease in sorted(disease_phrase_counts.keys()):
            phrases = disease_phrase_counts[disease]
            # 按频次降序排列
            for phrase, count in sorted(phrases.items(), key=lambda x: x[1], reverse=True):
                writer.writerow([disease, phrase, count])

    # 输出统计信息
    total_diseases = len(disease_phrase_counts)
    total_phrases = sum(len(phrases) for phrases in disease_phrase_counts.values())
    total_pairs = sum(sum(phrases.values()) for phrases in disease_phrase_counts.values())

    print(f"处理完成!")
    print(f"总记录数: {total_records}")
    print(f"疾病种类数: {total_diseases}")
    print(f"短语类型总数: {total_phrases}")
    print(f"疾病-短语配对总数: {total_pairs}")
    print(f"输出文件: {output_csv}")

    # 打印每个疾病的短语数量
    print("\n各疾病的短语数量:")
    for disease in sorted(disease_phrase_counts.keys()):
        print(f"  {disease}: {len(disease_phrase_counts[disease])} 种短语, "
              f"{sum(disease_phrase_counts[disease].values())} 次出现")

    return disease_phrase_counts


if __name__ == "__main__":
    # 数据路径
    jsonl_path = "data/mimic-cxr-a/all_structured_reports_normalized.jsonl"
    output_csv = "disease_phrase_counts.csv"

    # 检查文件是否存在
    if not Path(jsonl_path).exists():
        print(f"错误: 文件不存在 - {jsonl_path}")
        exit(1)

    # 执行提取
    extract_disease_phrases(jsonl_path, output_csv)
