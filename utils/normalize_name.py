#!/usr/bin/env python3
"""
统一MIMIC-CXR-A数据集中疾病名称的大小写（转为小写）
"""

import json
import os
import shutil
from typing import Dict, List
from collections import Counter

def normalize_disease_names_in_jsonl(input_path: str, output_path: str, backup: bool = True):
    """
    统一JSONL文件中的疾病名称为小写
    
    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径  
        backup: 是否创建备份文件
    """
    
    # 创建备份
    if backup and input_path == output_path:
        backup_path = input_path + '.backup'
        print(f"创建备份文件: {backup_path}")
        shutil.copy2(input_path, backup_path)
    
    # 统计信息
    total_records = 0
    modified_records = 0
    original_diseases = Counter()
    normalized_diseases = Counter()
    
    print(f"正在处理文件: {input_path}")
    print(f"输出文件: {output_path}")
    
    with open(input_path, 'r', encoding='utf-8') as infile, \
         open(output_path, 'w', encoding='utf-8') as outfile:
        
        for line_num, line in enumerate(infile, 1):
            if not line.strip():
                continue
                
            total_records += 1
            record_modified = False
            
            try:
                record = json.loads(line)
                
                # 处理 positive_findings
                if 'positive_findings' in record:
                    for finding in record['positive_findings']:
                        if isinstance(finding, dict) and 'disease_name' in finding:
                            original_name = finding['disease_name']
                            normalized_name = original_name.lower()
                            
                            original_diseases[original_name] += 1
                            normalized_diseases[normalized_name] += 1
                            
                            if original_name != normalized_name:
                                finding['disease_name'] = normalized_name
                                record_modified = True
                
                # 处理 negative_findings
                if 'negative_findings' in record:
                    new_negative_findings = []
                    for disease in record['negative_findings']:
                        if disease:
                            original_name = disease
                            normalized_name = disease.lower()
                            
                            original_diseases[original_name] += 1
                            normalized_diseases[normalized_name] += 1
                            
                            new_negative_findings.append(normalized_name)
                            
                            if original_name != normalized_name:
                                record_modified = True
                        else:
                            new_negative_findings.append(disease)
                    
                    record['negative_findings'] = new_negative_findings
                
                if record_modified:
                    modified_records += 1
                
                # 写入处理后的记录
                outfile.write(json.dumps(record, ensure_ascii=False) + '\n')
                
            except json.JSONDecodeError as e:
                print(f"第{line_num}行JSON解析错误: {e}")
                # 对于无法解析的行，直接写入原内容
                outfile.write(line)
                continue
            except Exception as e:
                print(f"第{line_num}行处理错误: {e}")
                outfile.write(line)
                continue
            
            # 显示进度
            if line_num % 10000 == 0:
                print(f"已处理 {line_num} 行，修改了 {modified_records} 条记录...")
    
    print(f"\n处理完成!")
    print(f"总记录数: {total_records}")
    print(f"修改记录数: {modified_records}")
    print(f"修改比例: {modified_records/total_records*100:.2f}%")
    
    return {
        'total_records': total_records,
        'modified_records': modified_records,
        'original_diseases': original_diseases,
        'normalized_diseases': normalized_diseases
    }

def analyze_normalization_impact(stats: Dict):
    """
    分析标准化对疾病名称的影响
    """
    print(f"\n{'='*80}")
    print(f"疾病名称标准化影响分析")
    print(f"{'='*80}")
    
    original_diseases = stats['original_diseases']
    normalized_diseases = stats['normalized_diseases']
    
    # 找出被合并的疾病名称
    original_unique = set(original_diseases.keys())
    normalized_unique = set(normalized_diseases.keys())
    
    print(f"标准化前疾病种类: {len(original_unique)}")
    print(f"标准化后疾病种类: {len(normalized_unique)}")
    print(f"减少疾病种类: {len(original_unique) - len(normalized_unique)}")
    
    # 找出大小写变体
    case_variants = {}
    for original in original_unique:
        normalized = original.lower()
        if normalized in case_variants:
            case_variants[normalized].append(original)
        else:
            case_variants[normalized] = [original]
    
    # 只显示有多个变体的疾病
    merged_diseases = {k: v for k, v in case_variants.items() if len(v) > 1}
    
    if merged_diseases:
        print(f"\n发现 {len(merged_diseases)} 组大小写变体被合并:")
        print(f"{'标准化后名称':<35} {'原始变体':<50} {'合并频次'}")
        print(f"{'-'*85}")
        
        for normalized_name, variants in merged_diseases.items():
            total_freq = sum(original_diseases[v] for v in variants)
            variants_str = ', '.join(variants)
            print(f"{normalized_name:<35} {variants_str:<50} {total_freq}")
    else:
        print(f"\n✅ 没有发现需要合并的大小写变体")

def validate_normalization(original_path: str, normalized_path: str):
    """
    验证标准化结果
    """
    print(f"\n{'='*80}")
    print(f"验证标准化结果")
    print(f"{'='*80}")
    
    # 统计原始文件中的疾病
    original_diseases = set()
    with open(original_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                # positive_findings
                for finding in record.get('positive_findings', []):
                    if isinstance(finding, dict):
                        disease = finding.get('disease_name', '')
                        if disease:
                            original_diseases.add(disease)
                # negative_findings  
                for disease in record.get('negative_findings', []):
                    if disease:
                        original_diseases.add(disease)
            except:
                continue
    
    # 统计标准化后文件中的疾病
    normalized_diseases = set()
    with open(normalized_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                # positive_findings
                for finding in record.get('positive_findings', []):
                    if isinstance(finding, dict):
                        disease = finding.get('disease_name', '')
                        if disease:
                            normalized_diseases.add(disease)
                # negative_findings
                for disease in record.get('negative_findings', []):
                    if disease:
                        normalized_diseases.add(disease)
            except:
                continue
    
    print(f"原始文件疾病种类: {len(original_diseases)}")
    print(f"标准化后疾病种类: {len(normalized_diseases)}")
    
    # 检查是否所有疾病都是小写
    non_lowercase = [d for d in normalized_diseases if d != d.lower()]
    if non_lowercase:
        print(f"⚠️  发现未转换为小写的疾病: {non_lowercase}")
    else:
        print(f"✅ 所有疾病名称都已转换为小写")
    
    return len(original_diseases), len(normalized_diseases)

def main():
    # 文件路径
    input_file = "/home/y530/handsome/DACG/data/mimic-cxr-a/all_structured_reports.jsonl"
    output_file = "/home/y530/handsome/DACG/data/mimic-cxr-a/all_structured_reports_normalized.jsonl"
    
    if not os.path.exists(input_file):
        print(f"输入文件不存在: {input_file}")
        return
    
    print("开始统一疾病名称大小写...")
    print("⚠️  这将创建一个新的标准化数据文件")
    
    # 执行标准化
    stats = normalize_disease_names_in_jsonl(input_file, output_file, backup=True)
    
    # 分析影响
    analyze_normalization_impact(stats)
    
    # 验证结果
    validate_normalization(input_file, output_file)
    
    # 保存统计报告
    report_file = "disease_normalization_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            'input_file': input_file,
            'output_file': output_file,
            'total_records': stats['total_records'],
            'modified_records': stats['modified_records'],
            'original_disease_count': len(stats['original_diseases']),
            'normalized_disease_count': len(stats['normalized_diseases']),
            'original_diseases': dict(stats['original_diseases']),
            'normalized_diseases': dict(stats['normalized_diseases'])
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n标准化完成!")
    print(f"标准化后的文件: {output_file}")
    print(f"统计报告: {report_file}")
    print(f"原始文件备份: {input_file}.backup")
    
    # 询问是否替换原文件
    print(f"\n如果确认标准化结果正确，可以执行以下命令替换原文件:")
    print(f"mv {output_file} {input_file}")

if __name__ == "__main__":
    main()