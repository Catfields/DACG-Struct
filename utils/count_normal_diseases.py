#!/usr/bin/env python3
"""
统计标准化后MIMIC-CXR-A数据集中疾病的覆盖率和频度
"""

import json
import pandas as pd
from collections import Counter, defaultdict
from typing import Dict, List, Tuple
import os

def analyze_normalized_dataset(data_path: str) -> Dict:
    """
    分析标准化后数据集中的疾病覆盖率
    """
    print(f"正在分析标准化后的数据文件: {data_path}")
    
    # 统计变量
    positive_counter = Counter()
    negative_counter = Counter()
    total_counter = Counter()
    
    # 统计每种疾病在每个样本中的出现情况
    sample_with_disease = defaultdict(int)  # 包含该疾病的样本数量
    
    total_samples = 0
    valid_samples = 0
    samples_with_positive_findings = 0
    samples_with_negative_findings = 0
    
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
                positive_findings = record.get('positive_findings', [])
                if positive_findings:
                    samples_with_positive_findings += 1
                
                for finding in positive_findings:
                    if isinstance(finding, dict):
                        disease_name = finding.get('disease_name', '')
                        if disease_name:
                            positive_counter[disease_name] += 1
                            total_counter[disease_name] += 1
                            current_sample_diseases.add(disease_name)
                
                # 统计negative_findings
                negative_findings = record.get('negative_findings', [])
                if negative_findings:
                    samples_with_negative_findings += 1
                
                for disease in negative_findings:
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
    print(f"有positive_findings的样本数: {samples_with_positive_findings}")
    print(f"有negative_findings的样本数: {samples_with_negative_findings}")
    print(f"发现的疾病种类: {len(total_counter)}")
    
    return {
        'positive_counter': positive_counter,
        'negative_counter': negative_counter, 
        'total_counter': total_counter,
        'sample_with_disease': sample_with_disease,
        'total_samples': total_samples,
        'valid_samples': valid_samples,
        'samples_with_positive_findings': samples_with_positive_findings,
        'samples_with_negative_findings': samples_with_negative_findings
    }

def print_coverage_analysis(stats: Dict):
    """
    打印疾病覆盖率分析结果
    """
    print(f"\n{'='*100}")
    print(f"标准化后数据集疾病覆盖率分析")
    print(f"{'='*100}")
    
    total_samples = stats['valid_samples']
    
    # 按总频次排序
    sorted_diseases = sorted(stats['total_counter'].keys(), 
                           key=lambda d: stats['total_counter'][d], 
                           reverse=True)
    
    print(f"\n{'疾病名称':<35} {'正例':<8} {'负例':<8} {'总计':<8} {'样本数':<8} {'覆盖率':<10} {'正例率':<10} {'类型'}")
    print(f"{'-'*110}")
    
    for disease in sorted_diseases:
        pos_count = stats['positive_counter'].get(disease, 0)
        neg_count = stats['negative_counter'].get(disease, 0)
        total_count = stats['total_counter'][disease]
        sample_count = stats['sample_with_disease'][disease]
        
        # 覆盖率：包含该疾病的样本占总样本的百分比
        coverage_rate = (sample_count / total_samples) * 100 if total_samples > 0 else 0
        
        # 正例率：正例占该疾病总提及次数的百分比
        positive_rate = (pos_count / total_count) * 100 if total_count > 0 else 0
        
        # 判断疾病类型
        if pos_count > 0 and neg_count > 0:
            disease_type = "正负例"
        elif pos_count > 0:
            disease_type = "仅正例"
        elif neg_count > 0:
            disease_type = "仅负例"
        else:
            disease_type = "未出现"
        
        print(f"{disease:<35} {pos_count:<8} {neg_count:<8} {total_count:<8} {sample_count:<8} {coverage_rate:<9.2f}% {positive_rate:<9.2f}% {disease_type}")

def print_summary_statistics(stats: Dict):
    """
    打印汇总统计信息
    """
    print(f"\n{'='*100}")
    print(f"汇总统计")
    print(f"{'='*100}")
    
    total_diseases = len(stats['total_counter'])
    total_samples = stats['valid_samples']
    
    # 按覆盖率分组
    coverage_ranges = {
        'very_high': (50.0, 100.0),     # 50%以上
        'high': (20.0, 50.0),           # 20%-50%
        'medium': (5.0, 20.0),          # 5%-20%
        'low': (1.0, 5.0),              # 1%-5%
        'very_low': (0.1, 1.0),         # 0.1%-1%
        'rare': (0.0, 0.1)              # <0.1%
    }
    
    range_counts = {name: [] for name in coverage_ranges}
    
    for disease, total_count in stats['total_counter'].items():
        sample_count = stats['sample_with_disease'][disease]
        coverage_rate = (sample_count / total_samples) * 100 if total_samples > 0 else 0
        
        for range_name, (min_val, max_val) in coverage_ranges.items():
            if min_val <= coverage_rate < max_val:
                range_counts[range_name].append((disease, coverage_rate))
                break
    
    print(f"疾病覆盖率分布:")
    print(f"{'覆盖率范围':<15} {'疾病数量':<10} {'占比':<10} {'示例疾病'}")
    print(f"{'-'*80}")
    
    for range_name, disease_list in range_counts.items():
        min_val, max_val = coverage_ranges[range_name]
        count = len(disease_list)
        percentage = (count / total_diseases) * 100 if total_diseases > 0 else 0
        
        if max_val == 100.0:
            range_str = f"{min_val}%-{max_val}%"
        else:
            range_str = f"{min_val}%-{max_val}%"
        
        # 显示前3个疾病作为示例
        examples = [d[0] for d in sorted(disease_list, key=lambda x: x[1], reverse=True)[:3]]
        examples_str = ", ".join(examples) if examples else "无"
        
        print(f"{range_str:<15} {count:<10} {percentage:<9.1f}% {examples_str}")
    
    # 正负例分布
    print(f"\n疾病类型分布:")
    positive_only = sum(1 for d in stats['total_counter'] 
                       if stats['positive_counter'].get(d, 0) > 0 and stats['negative_counter'].get(d, 0) == 0)
    negative_only = sum(1 for d in stats['total_counter'] 
                       if stats['positive_counter'].get(d, 0) == 0 and stats['negative_counter'].get(d, 0) > 0)
    both = sum(1 for d in stats['total_counter'] 
              if stats['positive_counter'].get(d, 0) > 0 and stats['negative_counter'].get(d, 0) > 0)
    
    print(f"  仅正例疾病: {positive_only} 种 ({positive_only/total_diseases*100:.1f}%)")
    print(f"  仅负例疾病: {negative_only} 种 ({negative_only/total_diseases*100:.1f}%)")
    print(f"  正负例疾病: {both} 种 ({both/total_diseases*100:.1f}%)")
    
    # Top疾病
    print(f"\n高覆盖率疾病 (前10名):")
    top_diseases = sorted(stats['total_counter'].items(), 
                         key=lambda x: stats['sample_with_disease'][x[0]], 
                         reverse=True)[:10]
    
    for i, (disease, total_count) in enumerate(top_diseases, 1):
        sample_count = stats['sample_with_disease'][disease]
        coverage_rate = (sample_count / total_samples) * 100
        print(f"  {i:2d}. {disease:<30} {coverage_rate:6.2f}% ({sample_count:,} 样本)")

def compare_with_original(original_report_path: str, stats: Dict):
    """
    与原始统计进行对比
    """
    if not os.path.exists(original_report_path):
        print(f"\n⚠️  未找到原始统计报告: {original_report_path}")
        return
    
    print(f"\n{'='*100}")
    print(f"与标准化前对比")
    print(f"{'='*100}")
    
    with open(original_report_path, 'r', encoding='utf-8') as f:
        original_stats = json.load(f)
    
    print(f"标准化前疾病种类: {original_stats.get('original_disease_count', 'N/A')}")
    print(f"标准化后疾病种类: {len(stats['total_counter'])}")
    print(f"减少疾病种类: {original_stats.get('original_disease_count', 0) - len(stats['total_counter'])}")

def main():
    # 文件路径
    normalized_file = "/home/y530/handsome/DACG/data/mimic-cxr-a/all_structured_reports_normalized.jsonl"
    original_file = "/home/y530/handsome/DACG/data/mimic-cxr-a/all_structured_reports.jsonl"
    
    # 检查标准化文件是否存在
    if os.path.exists(normalized_file):
        data_file = normalized_file
        print("使用标准化后的数据文件")
    elif os.path.exists(original_file):
        data_file = original_file
        print("⚠️  标准化文件不存在，使用原始文件")
    else:
        print(f"数据文件不存在: {normalized_file} 或 {original_file}")
        return
    
    print("开始分析疾病覆盖率...")
    print("这可能需要几分钟时间...")
    
    # 分析数据
    stats = analyze_normalized_dataset(data_file)
    
    # 打印结果
    print_coverage_analysis(stats)
    print_summary_statistics(stats)
    
    # 与原始数据对比
    compare_with_original("disease_normalization_report.json", stats)
    
    # 保存结果
    output_file = "normalized_disease_coverage_analysis.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'analysis_file': data_file,
            'total_samples': stats['total_samples'],
            'valid_samples': stats['valid_samples'],
            'disease_count': len(stats['total_counter']),
            'positive_counter': dict(stats['positive_counter']),
            'negative_counter': dict(stats['negative_counter']),
            'total_counter': dict(stats['total_counter']),
            'sample_with_disease': dict(stats['sample_with_disease']),
            'samples_with_positive_findings': stats['samples_with_positive_findings'],
            'samples_with_negative_findings': stats['samples_with_negative_findings']
        }, f, ensure_ascii=False, indent=2)
    
    # 保存CSV报告
    csv_file = "normalized_disease_coverage_report.csv"
    csv_data = []
    
    for disease in stats['total_counter']:
        pos_count = stats['positive_counter'].get(disease, 0)
        neg_count = stats['negative_counter'].get(disease, 0)
        total_count = stats['total_counter'][disease]
        sample_count = stats['sample_with_disease'][disease]
        coverage_rate = (sample_count / stats['valid_samples']) * 100
        positive_rate = (pos_count / total_count) * 100 if total_count > 0 else 0
        
        csv_data.append({
            'disease': disease,
            'positive_count': pos_count,
            'negative_count': neg_count,
            'total_count': total_count,
            'sample_count': sample_count,
            'coverage_rate_percent': round(coverage_rate, 2),
            'positive_rate_percent': round(positive_rate, 2)
        })
    
    df = pd.DataFrame(csv_data)
    df = df.sort_values('coverage_rate_percent', ascending=False)
    df.to_csv(csv_file, index=False, encoding='utf-8')
    
    print(f"\n分析完成!")
    print(f"详细结果: {output_file}")
    print(f"CSV报告: {csv_file}")

if __name__ == "__main__":
    main()