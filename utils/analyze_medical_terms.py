#!/usr/bin/env python3
"""
统计MIMIC-CXR-A数据集中的疾病名称、严重程度和解剖位置
"""

import json
from collections import Counter
from typing import Set, List, Dict

def analyze_medical_terms(file_path: str):
    """分析医疗术语统计"""
    
    disease_names = set()
    severity_levels = set()
    anatomical_locations = set()
    probability_values = set()
    
    total_records = 0
    records_with_positive_findings = 0
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            # 解析JSON数据
            try:
                # 跳过行号前缀
                if '|' in line:
                    json_str = line.split('|', 1)[1].strip()
                else:
                    json_str = line
                    
                data = json.loads(json_str)
                total_records += 1
                
                # 处理阳性发现
                positive_findings = data.get('positive_findings', [])
                if positive_findings:
                    records_with_positive_findings += 1
                    
                    for finding in positive_findings:
                        # 提取疾病名称
                        disease_name = finding.get('disease_name')
                        if disease_name:
                            disease_name = str(disease_name).strip()
                            if disease_name:
                                disease_names.add(disease_name.lower())
                        
                        # 提取严重程度
                        severity = finding.get('severity')
                        if severity:
                            severity = str(severity).strip()
                            if severity:
                                severity_levels.add(severity.lower())
                        
                        # 提取解剖位置
                        location = finding.get('anatomical_location')
                        if location:
                            location = str(location).strip()
                            if location and location.lower() != 'none':
                                # 多个位置可能用逗号或"and"分隔
                                locations = location.replace(' and ', ', ').split(', ')
                                for loc in locations:
                                    loc = loc.strip()
                                    if loc and loc.lower() != 'none':
                                        anatomical_locations.add(loc.lower())
                        
                        # 提取概率值
                        probability = finding.get('probability')
                        if probability is not None:
                            probability_values.add(probability)
                
                # 处理阴性发现（可选，用于完整性）
                negative_findings = data.get('negative_findings', [])
                for disease in negative_findings:
                    if disease:
                        disease_names.add(disease.lower())
                        
            except (json.JSONDecodeError, IndexError) as e:
                print(f"解析错误: {line[:100]}... {e}")
                continue
    
    # 统计信息
    print("=" * 60)
    print("MIMIC-CXR-A 数据集统计分析")
    print("=" * 60)
    print(f"总记录数: {total_records:,}")
    print(f"有阳性发现的记录数: {records_with_positive_findings:,}")
    print(f"无阳性发现的记录数: {total_records - records_with_positive_findings:,}")
    print()
    
    # 疾病名称统计
    print(f"疾病名称统计 (共 {len(disease_names)} 个):")
    print("-" * 40)
    disease_list = sorted(list(disease_names))
    for i, disease in enumerate(disease_list, 1):
        print(f"{i:3d}. {disease}")
    print()
    
    # 严重程度统计
    print(f"严重程度统计 (共 {len(severity_levels)} 个):")
    print("-" * 40)
    severity_list = sorted(list(severity_levels))
    for i, severity in enumerate(severity_list, 1):
        print(f"{i:2d}. {severity}")
    print()
    
    # 解剖位置统计
    print(f"解剖位置统计 (共 {len(anatomical_locations)} 个):")
    print("-" * 40)
    location_list = sorted(list(anatomical_locations))
    for i, location in enumerate(location_list, 1):
        print(f"{i:3d}. {location}")
    print()
    
    # 概率值统计
    print(f"概率值统计 (共 {len(probability_values)} 个):")
    print("-" * 40)
    probability_list = sorted(list(probability_values))
    for i, prob in enumerate(probability_list, 1):
        print(f"{i:2d}. {prob}")
    print()
    
    # 保存结果到文件
    output_file = "/home/y530/handsome/DACG/medical_terms_statistics.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("MIMIC-CXR-A 数据集统计分析\n")
        f.write("=" * 60 + "\n")
        f.write(f"总记录数: {total_records:,}\n")
        f.write(f"有阳性发现的记录数: {records_with_positive_findings:,}\n")
        f.write(f"无阳性发现的记录数: {total_records - records_with_positive_findings:,}\n")
        f.write("\n")
        
        f.write(f"疾病名称统计 (共 {len(disease_names)} 个):\n")
        f.write("-" * 40 + "\n")
        for i, disease in enumerate(disease_list, 1):
            f.write(f"{i:3d}. {disease}\n")
        f.write("\n")
        
        f.write(f"严重程度统计 (共 {len(severity_levels)} 个):\n")
        f.write("-" * 40 + "\n")
        for i, severity in enumerate(severity_list, 1):
            f.write(f"{i:2d}. {severity}\n")
        f.write("\n")
        
        f.write(f"解剖位置统计 (共 {len(anatomical_locations)} 个):\n")
        f.write("-" * 40 + "\n")
        for i, location in enumerate(location_list, 1):
            f.write(f"{i:3d}. {location}\n")
        f.write("\n")
        
        f.write(f"概率值统计 (共 {len(probability_values)} 个):\n")
        f.write("-" * 40 + "\n")
        probability_list = sorted(list(probability_values))
        for i, prob in enumerate(probability_list, 1):
            f.write(f"{i:2d}. {prob}\n")
    
    print(f"详细结果已保存到: {output_file}")

if __name__ == "__main__":
    file_path = "/home/y530/handsome/DACG/data/mimic-cxr-a/all_structured_reports_normalized.jsonl"
    analyze_medical_terms(file_path)