#!/usr/bin/env python3
"""
清理 negative_findings 中不在 positive_findings 21种有效疾病列表中的疾病
根据分析，positive_findings 中的21种有效疾病（不包括 no finding）为：
"""

import json
import os

# positive_findings 中出现的21种有效疾病（按频率排序）
VALID_DISEASES = {
    'atelectasis',
    'lung opacity',
    'support devices',
    'pleural effusion',
    'cardiomegaly',
    'edema',
    'pneumonia',
    'tortuosity of the thoracic aorta',
    'calcification',
    'emphysema',
    'consolidation',
    'fracture',
    'lung lesion',
    'enlarged cardiomediastinum',
    'scoliosis',
    'blunting of costophrenic angle',
    'hernia',
    'pneumothorax',
    'pleural thickening',
    'granuloma',
    'pleural other'
}

def clean_negative_findings(input_file, output_file=None):
    """
    清理 negative_findings 中不在有效疾病列表中的疾病

    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径，如果为 None 则覆盖原文件
    """
    if output_file is None:
        output_file = input_file + '.tmp'

    processed_count = 0
    modified_count = 0
    removed_diseases_count = {}

    # 统计处理前的疾病分布
    before_stats = {}
    after_stats = {}

    try:
        with open(input_file, 'r', encoding='utf-8') as infile, \
             open(output_file, 'w', encoding='utf-8') as outfile:

            for line_num, line in enumerate(infile, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    # 处理行号前缀
                    if '|' in line:
                        pipe_index = line.find('|')
                        json_str = line[pipe_index + 1:].strip()
                    else:
                        json_str = line

                    # 解析 JSON 对象
                    data = json.loads(json_str)

                    # 处理 negative_findings
                    if 'negative_findings' in data and isinstance(data['negative_findings'], list):
                        original_count = len(data['negative_findings'])

                        # 统计处理前的疾病
                        for disease in data['negative_findings']:
                            disease_str = disease.strip()
                            before_stats[disease_str] = before_stats.get(disease_str, 0) + 1

                        # 过滤无效疾病
                        valid_negative_findings = []
                        for disease in data['negative_findings']:
                            disease_str = disease.strip()
                            # 标准化疾病名称（处理前后空格）
                            if disease_str in VALID_DISEASES:
                                valid_negative_findings.append(disease_str)
                            else:
                                removed_diseases_count[disease_str] = removed_diseases_count.get(disease_str, 0) + 1

                        # 更新数据
                        data['negative_findings'] = valid_negative_findings

                        # 统计处理后的疾病
                        for disease in valid_negative_findings:
                            after_stats[disease_str] = after_stats.get(disease_str, 0) + 1

                        # 检查是否有修改
                        if len(valid_negative_findings) != original_count:
                            modified_count += 1

                    # 写入处理后的数据
                    if '|' in line:
                        outfile.write(f"{line[:pipe_index + 1]}{json.dumps(data, ensure_ascii=False)}\n")
                    else:
                        outfile.write(json.dumps(data, ensure_ascii=False) + '\n')
                    processed_count += 1

                except json.JSONDecodeError as e:
                    print(f"警告: 第 {line_num} 行 JSON 解析错误: {e}")
                    outfile.write(line + '\n')
                    continue

                # 显示进度
                if line_num % 10000 == 0:
                    print(f"已处理 {line_num} 行...")

        print(f"处理完成！")
        print(f"总共处理: {processed_count} 行")
        print(f"修改的行数: {modified_count} 行")

        print(f"\n被删除的疾病统计:")
        for disease, count in sorted(removed_diseases_count.items(), key=lambda x: x[1], reverse=True):
            print(f"  {disease}: {count}")

        print(f"\n处理前 negative_findings 中疾病分布（前20）:")
        for disease, count in sorted(before_stats.items(), key=lambda x: x[1], reverse=True)[:20]:
            print(f"  {disease}: {count}")

        print(f"\n处理后 negative_findings 中疾病分布:")
        for disease, count in sorted(after_stats.items(), key=lambda x: x[1], reverse=True):
            print(f"  {disease}: {count}")

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

def show_valid_diseases():
    """显示有效疾病列表"""
    print("有效疾病列表（共21种）:")
    print("=" * 50)
    for i, disease in enumerate(sorted(VALID_DISEASES), 1):
        print(f"{i:2d}. {disease}")

if __name__ == "__main__":
    input_file = "data/mimic-cxr-a/all_structured_reports_normalized.jsonl"

    print("开始清理 negative_findings 中的无效疾病...")
    show_valid_diseases()
    print()

    clean_negative_findings(input_file)