#!/usr/bin/env python3
"""
统计MIMIC-CXR-A数据集中疾病的出现频度
"""

import json
import pandas as pd
from collections import Counter, defaultdict
from typing import Dict, List, Tuple
import os

# 从训练集中提取的44种疾病
TRAIN_DISEASES = [
    "Atelectasis", "Blunting of costophrenic angle", "Calcification", "Cardiomegaly", 
    "Consolidation", "Edema", "Emphysema", "Enlarged Cardiomediastinum", "Fracture", 
    "Granuloma", "Hernia", "Lung Lesion", "Lung Opacity", "No Finding", 
    "Pleural Effusion", "Pleural Other", "Pleural Thickening", "Pneumonia", 
    "Pneumothorax", "Scoliosis", "Support Devices", "Tortuosity of the thoracic aorta", 
    "airway obstruction", "atelectasis", "bronchiectasis", "bronchitis", "calcinosis", 
    "cardiomegaly", "consolidation", "edema", "emphysema", "fibrosis", "hiatal hernia", 
    "lung cancer", "mass", "metastatic disease", "nodule", "pleural effusion", 
    "pleural thickening", "pneumonia", "pneumothorax", "pulmonary hypertension", 
    "sarcoidosis", "tuberculosis"
]

def analyze_disease_frequency(data_path: str) -> Dict:
    """
    分析疾病在数据集中的出现频度
    """
    print(f"正在分析数据文件: {data_path}")
    
    # 统计变量
    positive_counter = Counter()
    negative_counter = Counter()
    total_counter = Counter()
    
    # 统计每种疾病在每个样本中的出现情况
    sample_with_disease = defaultdict(int)  # 包含该疾病的样本数量
    
    total_samples = 0
    valid_samples = 0
    
    with open(data_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
                
            total_samples += 1
            
            try:
                record = json.loads(line)
                valid_samples += 1
                
                # 当前样本中出现的疾病（去重）
                current_sample_diseases = set()
                
                # 统计positive_findings
                for finding in record.get('positive_findings', []):
                    if isinstance(finding, dict):
                        disease_name = finding.get('disease_name', '')
                        if disease_name:
                            positive_counter[disease_name] += 1
                            total_counter[disease_name] += 1
                            current_sample_diseases.add(disease_name)
                
                # 统计negative_findings
                for disease in record.get('negative_findings', []):
                    if disease:
                        negative_counter[disease] += 1
                        total_counter[disease] += 1
                        current_sample_diseases.add(disease)
                
                # 统计包含每种疾病的样本数量
                for disease in current_sample_diseases:
                    sample_with_disease[disease] += 1
                    
            except json.JSONDecodeError as e:
                print(f"第{line_num}行JSON解析错误: {e}")
                continue
            except Exception as e:
                print(f"第{line_num}行处理错误: {e}")
                continue
            
            # 每处理10000行显示进度
            if line_num % 10000 == 0:
                print(f"已处理 {line_num} 行...")
    
    print(f"\n数据统计:")
    print(f"总样本数: {total_samples}")
    print(f"有效样本数: {valid_samples}")
    print(f"发现的疾病种类: {len(total_counter)}")
    
    return {
        'positive_counter': positive_counter,
        'negative_counter': negative_counter, 
        'total_counter': total_counter,
        'sample_with_disease': sample_with_disease,
        'total_samples': total_samples,
        'valid_samples': valid_samples
    }

def find_case_variants(disease_list: List[str]) -> Dict[str, List[str]]:
    """
    查找大小写变体
    """
    case_variants = defaultdict(list)
    
    for disease in disease_list:
        # 将疾病名称转换为小写作为键
        lower_key = disease.lower()
        case_variants[lower_key].append(disease)
    
    # 只返回有多个变体的疾病
    return {k: v for k, v in case_variants.items() if len(v) > 1}

def merge_case_variants_stats(stats: Dict, variants: Dict[str, List[str]]):
    """
    合并大小写变体的统计数据
    """
    merged_stats = {
        'positive_counter': Counter(),
        'negative_counter': Counter(),
        'total_counter': Counter(),
        'sample_with_disease': defaultdict(int),
        'total_samples': stats['total_samples'],
        'valid_samples': stats['valid_samples']
    }
    
    # 创建疾病映射（所有变体映射到第一个出现的形式）
    disease_mapping = {}
    for lower_key, variant_list in variants.items():
        canonical_form = variant_list[0]  # 使用第一个作为标准形式
        for variant in variant_list:
            disease_mapping[variant] = canonical_form
    
    # 合并统计数据
    for disease in TRAIN_DISEASES:
        canonical_disease = disease_mapping.get(disease, disease)
        
        # 累加所有变体的数据
        if canonical_disease == disease:  # 如果这是标准形式
            # 找到所有映射到这个标准形式的变体
            all_variants = [d for d, canonical in disease_mapping.items() if canonical == disease]
            if not all_variants:  # 如果没有变体，就是它自己
                all_variants = [disease]
            
            for variant in all_variants:
                merged_stats['positive_counter'][canonical_disease] += stats['positive_counter'].get(variant, 0)
                merged_stats['negative_counter'][canonical_disease] += stats['negative_counter'].get(variant, 0)
                merged_stats['total_counter'][canonical_disease] += stats['total_counter'].get(variant, 0)
                merged_stats['sample_with_disease'][canonical_disease] += stats['sample_with_disease'].get(variant, 0)
    
    return merged_stats

def print_frequency_analysis(stats: Dict, train_diseases: List[str]):
    """
    打印频度分析结果
    """
    print(f"\n{'='*85}")
    print(f"训练集中44种疾病的频度分析")
    print(f"{'='*85}")
    
    # 检查大小写变体
    variants = find_case_variants(train_diseases)
    if variants:
        print(f"\n⚠️  发现大小写变体:")
        for lower_key, variant_list in variants.items():
            print(f"  {lower_key}: {variant_list}")
        
        # 提供合并后的统计
        print(f"\n📊 合并大小写变体后的统计:")
        merged_stats = merge_case_variants_stats(stats, variants)
        unique_diseases = list(set([variants[k.lower()][0] if k.lower() in variants else k for k in train_diseases]))
        print_detailed_stats(merged_stats, unique_diseases, "合并后")
    
    print(f"\n📋 原始统计（未合并大小写变体）:")
    print_detailed_stats(stats, train_diseases, "原始")

def print_detailed_stats(stats: Dict, diseases: List[str], title: str):
    """
    打印详细的统计信息
    """
    print(f"\n{title}疾病统计:")
    print(f"{'疾病名称':<35} {'正例':<8} {'负例':<8} {'总计':<8} {'样本率':<10} {'类型'}")
    print(f"{'-'*85}")
    
    # 按总频次排序
    sorted_diseases = sorted(diseases, 
                           key=lambda d: stats['total_counter'].get(d, 0), 
                           reverse=True)
    
    for disease in sorted_diseases:
        pos_count = stats['positive_counter'].get(disease, 0)
        neg_count = stats['negative_counter'].get(disease, 0)
        total_count = stats['total_counter'].get(disease, 0)
        sample_count = stats['sample_with_disease'].get(disease, 0)
        sample_rate = (sample_count / stats['valid_samples']) * 100 if stats['valid_samples'] > 0 else 0
        
        # 判断疾病类型
        if pos_count > 0 and neg_count > 0:
            disease_type = "正负例"
        elif pos_count > 0:
            disease_type = "仅正例"
        elif neg_count > 0:
            disease_type = "仅负例"
        else:
            disease_type = "未出现"
        
        print(f"{disease:<35} {pos_count:<8} {neg_count:<8} {total_count:<8} {sample_rate:<9.2f}% {disease_type}")
    
    # 统计摘要
    print(f"\n{title}统计摘要:")
    diseases_with_data = [d for d in diseases if stats['total_counter'].get(d, 0) > 0]
    diseases_without_data = [d for d in diseases if stats['total_counter'].get(d, 0) == 0]
    
    print(f"有数据的疾病: {len(diseases_with_data)} / {len(diseases)}")
    print(f"无数据的疾病: {len(diseases_without_data)} / {len(diseases)}")
    
    if diseases_without_data:
        print(f"无数据的疾病列表:")
        for disease in diseases_without_data:
            print(f"  - {disease}")
    
    # 频次分布
    freq_ranges = {
        'very_high': (10000, float('inf')),  # >10k
        'high': (5000, 10000),               # 5k-10k  
        'medium': (1000, 5000),              # 1k-5k
        'low': (100, 1000),                  # 100-1k
        'very_low': (1, 100),                # 1-100
        'none': (0, 1)                       # 0
    }
    
    range_counts = {name: 0 for name in freq_ranges}
    
    for disease in diseases:
        total_count = stats['total_counter'].get(disease, 0)
        for range_name, (min_val, max_val) in freq_ranges.items():
            if min_val <= total_count < max_val:
                range_counts[range_name] += 1
                break
    
    print(f"\n频次分布:")
    for range_name, count in range_counts.items():
        min_val, max_val = freq_ranges[range_name]
        if max_val == float('inf'):
            range_str = f">{min_val}"
        elif min_val == 0:
            range_str = "0"
        else:
            range_str = f"{min_val}-{max_val-1}"
        print(f"  {range_str:>10}: {count:>3} 种疾病")

def main():
    data_path = "/home/y530/handsome/DACG/data/mimic-cxr-a/all_structured_reports.jsonl"
    
    if not os.path.exists(data_path):
        print(f"数据文件不存在: {data_path}")
        return
    
    print("开始分析疾病频度...")
    print("这可能需要几分钟时间...")
    
    stats = analyze_disease_frequency(data_path)
    print_frequency_analysis(stats, TRAIN_DISEASES)
    
    # 保存详细结果到文件
    output_file = "disease_frequency_analysis.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        # 转换Counter对象为普通字典以便JSON序列化
        json_stats = {
            'positive_counter': dict(stats['positive_counter']),
            'negative_counter': dict(stats['negative_counter']),
            'total_counter': dict(stats['total_counter']),
            'sample_with_disease': dict(stats['sample_with_disease']),
            'total_samples': stats['total_samples'],
            'valid_samples': stats['valid_samples'],
            'train_diseases': TRAIN_DISEASES
        }
        json.dump(json_stats, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细结果已保存到: {output_file}")
    
    # 保存简化的CSV报告
    csv_file = "disease_frequency_report.csv"
    csv_data = []
    
    for disease in TRAIN_DISEASES:
        pos_count = stats['positive_counter'].get(disease, 0)
        neg_count = stats['negative_counter'].get(disease, 0)
        total_count = stats['total_counter'].get(disease, 0)
        sample_count = stats['sample_with_disease'].get(disease, 0)
        sample_rate = (sample_count / stats['valid_samples']) * 100 if stats['valid_samples'] > 0 else 0
        
        csv_data.append({
            'disease': disease,
            'positive_count': pos_count,
            'negative_count': neg_count,
            'total_count': total_count,
            'sample_count': sample_count,
            'sample_rate_percent': round(sample_rate, 2)
        })
    
    df = pd.DataFrame(csv_data)
    df = df.sort_values('total_count', ascending=False)
    df.to_csv(csv_file, index=False, encoding='utf-8')
    
    print(f"CSV报告已保存到: {csv_file}")

if __name__ == "__main__":
    main()