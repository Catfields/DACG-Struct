#!/usr/bin/env python3
"""
将 all_structured_reports_normalized.jsonl 文件中的 severity 字段转换为数值标签
按照以下映射规则：
- 0: none (原值: none, None)
- 1: mild (原值: mild, very mild, slight)
- 2: moderate (原值: moderate, mild to moderate, mild-to-moderate, small to moderate)
- 3: severe (原值: severe, moderate to severe, moderate/severe, marked)
"""

import json
import os

def normalize_severity(severity_value):
    """
    将 severity 值标准化为数值标签

    Args:
        severity_value: 原始的 severity 值

    Returns:
        数值标签 (0, 1, 2, 3)
    """
    if severity_value is None:
        return 0

    # 转换为小写并去除空格
    severity_str = str(severity_value).lower().strip()

    # 定义映射规则
    severity_mapping = {
        # none -> 0
        'none': 0,
        '': 0,

        # mild -> 1
        'mild': 1,
        'very mild': 1,
        'slight': 1,

        # moderate -> 2
        'moderate': 2,
        'mild to moderate': 2,
        'mild-to-moderate': 2,
        'small to moderate': 2,

        # severe -> 3
        'severe': 3,
        'moderate to severe': 3,
        'moderate/severe': 3,
        'marked': 3,
    }

    return severity_mapping.get(severity_str, 0)  # 默认返回 0

def process_severity_fields(input_file, output_file=None):
    """
    处理 severity 字段，将其转换为数值标签

    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径，如果为 None 则覆盖原文件
    """
    if output_file is None:
        output_file = input_file + '.tmp'

    processed_count = 0
    modified_count = 0
    severity_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    original_severity_counts = {}

    try:
        with open(input_file, 'r', encoding='utf-8') as infile, \
             open(output_file, 'w', encoding='utf-8') as outfile:

            for line_num, line in enumerate(infile, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    # 处理行号前缀，格式可能是 "1| {"key": "value"}"
                    if '|' in line:
                        # 找到第一个竖线后面的位置
                        pipe_index = line.find('|')
                        json_str = line[pipe_index + 1:].strip()
                    else:
                        json_str = line

                    # 解析 JSON 对象
                    data = json.loads(json_str)

                    # 检查是否有 positive_findings 字段
                    if 'positive_findings' in data and isinstance(data['positive_findings'], list):
                        line_modified = False

                        # 遍历 positive_findings 中的每个对象
                        for finding in data['positive_findings']:
                            if isinstance(finding, dict) and 'severity' in finding:
                                original_severity = finding['severity']

                                # 统计原始 severity 值
                                original_severity_counts[original_severity] = original_severity_counts.get(original_severity, 0) + 1

                                # 转换为数值标签
                                numeric_severity = normalize_severity(original_severity)
                                severity_counts[numeric_severity] += 1

                                if original_severity != numeric_severity:
                                    finding['severity'] = numeric_severity
                                    line_modified = True

                        if line_modified:
                            modified_count += 1

                    # 写入处理后的数据，保持原有的行号前缀格式
                    if '|' in line:
                        outfile.write(f"{line[:pipe_index + 1]}{json.dumps(data, ensure_ascii=False)}\n")
                    else:
                        outfile.write(json.dumps(data, ensure_ascii=False) + '\n')
                    processed_count += 1

                except json.JSONDecodeError as e:
                    print(f"警告: 第 {line_num} 行 JSON 解析错误: {e}")
                    # 保持原行不变
                    outfile.write(line + '\n')
                    continue

                # 显示进度
                if line_num % 10000 == 0:
                    print(f"已处理 {line_num} 行...")

        print(f"处理完成！")
        print(f"总共处理: {processed_count} 行")
        print(f"修改的行数: {modified_count} 行")

        print(f"\n原始 severity 值统计:")
        for severity, count in sorted(original_severity_counts.items(), key=lambda x: str(x[0]) if x[0] is not None else 'None'):
            print(f"  {severity}: {count}")

        print(f"\n转换后的数值标签统计:")
        label_names = {0: 'none', 1: 'mild', 2: 'moderate', 3: 'severe'}
        for label, count in severity_counts.items():
            print(f"  {label} ({label_names[label]}): {count}")

        # 如果输出文件是临时文件，替换原文件
        if output_file.endswith('.tmp'):
            os.replace(output_file, input_file)
            print(f"\n已更新原文件: {input_file}")
        else:
            print(f"\n结果已保存到: {output_file}")

    except FileNotFoundError:
        print(f"错误: 找不到输入文件 {input_file}")
    except Exception as e:
        print(f"处理过程中发生错误: {e}")
        # 清理临时文件
        if output_file.endswith('.tmp') and os.path.exists(output_file):
            os.remove(output_file)

if __name__ == "__main__":
    input_file = "data/mimic-cxr-a/all_structured_reports_normalized.jsonl"

    print("开始处理 severity 字段转换为数值标签...")
    print("映射规则:")
    print("  0 (none): none, None")
    print("  1 (mild): mild, very mild, slight")
    print("  2 (moderate): moderate, mild to moderate, mild-to-moderate, small to moderate")
    print("  3 (severe): severe, moderate to severe, moderate/severe, marked")
    print()

    process_severity_fields(input_file)