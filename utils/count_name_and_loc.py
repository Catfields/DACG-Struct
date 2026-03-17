import json
from collections import defaultdict, Counter

def extract_disease_coverage_and_locations(jsonl_file):
    """
    从数据中自动提取阳性疾病的覆盖率和对应的位置词表
    """
    
    # 统计阳性疾病覆盖率 (疾病出现在多少个报告中)
    disease_coverage = defaultdict(set)  # 疾病名称 -> 报告ID集合
    disease_locations = defaultdict(Counter)  # 疾病名称 -> 位置信息计数器
    
    total_reports = 0
    error_count = 0
    
    print("正在读取和分析数据...")
    
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if line_num % 5000 == 0:
                print(f"处理进度: {line_num} 行，成功: {total_reports}，错误: {error_count}")
            
            # 跳过空行
            line = line.strip()
            if not line:
                continue
                
            try:
                # 移除行号前缀（如 "1| ", "2| " 等）
                if '|' in line:
                    # 找到第一个竖线位置，跳过它和后面的空格
                    pipe_index = line.find('|')
                    line = line[pipe_index + 1:].lstrip()

                data = json.loads(line)
                
                # 检查是否有metadata字段
                if 'metadata' not in data:
                    print(f"警告: 第{line_num}行缺少metadata字段")
                    error_count += 1
                    continue
                
                report_id = data['metadata']['id']
                total_reports += 1
                
                # 只处理阳性发现 (positive_findings)
                for finding in data.get('positive_findings', []):
                    disease_name = finding.get('disease_name', '')
                    
                    # 跳过"no finding"这种非实际疾病
                    if disease_name.lower() in ['no finding', 'no findings']:
                        continue
                    
                    location = finding.get('anatomical_location', '')
                    
                    # 记录疾病出现的报告
                    disease_coverage[disease_name].add(report_id)
                    
                    # 记录疾病对应的位置信息
                    if location and location.strip() and location != 'None':
                        # 清理位置信息
                        location = location.strip()
                        disease_locations[disease_name][location] += 1
                    
            except json.JSONDecodeError as e:
                error_count += 1
                if error_count <= 5:  # 只显示前5个错误的详细信息
                    print(f"警告: 第{line_num}行JSON解析错误: {e}")
                    print(f"  内容: {line[:100]}...")  # 显示前100个字符
                elif error_count == 6:
                    print(f"后续JSON解析错误将不再显示详细信息...")
                continue
            except Exception as e:
                error_count += 1
                print(f"警告: 第{line_num}行处理错误: {type(e).__name__}: {e}")
                continue
    
    print(f"\n总共处理了 {total_reports} 个报告")
    print(f"发现 {len(disease_coverage)} 种不同的阳性疾病（已过滤'no finding'）")
    print(f"错误行数: {error_count}")
    
    # 计算覆盖率并排序
    disease_stats = []
    for disease, report_ids in disease_coverage.items():
        coverage_count = len(report_ids)
        coverage_rate = coverage_count / total_reports * 100 if total_reports > 0 else 0
        disease_stats.append((disease, coverage_count, coverage_rate))
    
    # 按覆盖次数排序，取前30
    disease_stats.sort(key=lambda x: x[1], reverse=True)
    top_30_diseases = disease_stats[:30]
    
    return top_30_diseases, disease_locations, total_reports

def format_disease_location_output(top_30_diseases, disease_locations, total_reports):
    """
    格式化输出疾病及其对应的位置词表
    """
    
    if not top_30_diseases:
        print("没有找到任何疾病数据")
        return
    
    print("="*80)
    print("前30位阳性疾病覆盖率统计及其对应位置词表")
    print("="*80)
    
    for i, (disease, count, coverage_rate) in enumerate(top_30_diseases, 1):
        print(f"\n{i}. **{disease}**")
        print(f"   出现次数: {count} 次")
        print(f"   覆盖率: {coverage_rate:.2f}%")
        
        # 获取该疾病的位置信息
        locations = disease_locations.get(disease, Counter())
        
        if locations:
            print(f"   位置词表 (共 {len(locations)} 种位置，按出现频次排序):")
            # 按出现频次排序
            sorted_locations = locations.most_common()
            for location, freq in sorted_locations:
                print(f"   - {location} (出现{freq}次)")
        else:
            print("   位置词表: 无特定位置信息")
        
        print("-" * 60)

def export_location_vocabulary(top_30_diseases, disease_locations, output_file):
    """
    导出格式化的位置词表到文件
    """
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# 前30位阳性疾病及其位置词表\n\n")
        
        for i, (disease, count, coverage_rate) in enumerate(top_30_diseases, 1):
            f.write(f"## {i}. {disease}\n")
            f.write(f"- 出现次数: {count}\n")
            f.write(f"- 覆盖率: {coverage_rate:.2f}%\n")
            f.write(f"- 位置词表:\n")
            
            locations = disease_locations.get(disease, Counter())
            if locations:
                sorted_locations = locations.most_common()
                for location, freq in sorted_locations:
                    f.write(f"  - {location} (出现{freq}次)\n")
            else:
                f.write("  - 无特定位置\n")
            
            f.write("\n")
    
    print(f"位置词表已导出到: {output_file}")

def main():
    jsonl_file = "/home/y530/handsome/DACG/data/mimic-cxr-a/all_structured_reports_normalized.jsonl"
    output_file = "top30_diseases_location_vocabulary.md"
    
    print("开始分析阳性疾病覆盖率和位置词表...")
    
    # 提取疾病覆盖率和位置信息
    top_30_diseases, disease_locations, total_reports = extract_disease_coverage_and_locations(jsonl_file)
    
    # 控制台输出
    format_disease_location_output(top_30_diseases, disease_locations, total_reports)
    
    # 导出到文件
    if top_30_diseases:
        export_location_vocabulary(top_30_diseases, disease_locations, output_file)
    
    print(f"\n分析完成! 总共分析了 {total_reports} 个报告")
    print("=" * 80)

if __name__ == "__main__":
    main()