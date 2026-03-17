"""
按照 disease_schema.json 的规则重新统计概念

隔离规则：
1. support devices - 支持设备
2. no finding - 无异常
3. blunting_of_costophrenic_angle - secondary (enable_location=false)
4. pleural_other - fallback (enable_location=false)
5. scoliosis - 位置建模意义不大 (enable_location=false)
6. enlarged_cardiomediastinum - attribute (enable_location=false)
"""

import json
import csv
from collections import defaultdict, Counter
from pathlib import Path

# 疾病名称映射
DISEASE_NAME_MAP = {
    'blunting of costophrenic angle': 'blunting_of_costophrenic_angle',
    'lung opacity': 'lung_opacity',
    'lung lesion': 'lung_lesion',
    'pleural effusion': 'pleural_effusion',
    'pleural thickening': 'pleural_thickening',
    'pleural other': 'pleural_other',
    'tortuosity of the thoracic aorta': 'tortuosity_of_the_thoracic_aorta',
    'enlarged cardiomediastinum': 'enlarged_cardiomediastinum',
}

# Schema中定义的隔离疾病
ISOLATED_DISEASES = {
    'support devices',
    'no finding',
    'blunting_of_costophrenic_angle',
    'pleural_other',
    'scoliosis',
    'enlarged_cardiomediastinum',
}

# 按family分组的疾病
FAMILY_GROUPS = {
    'parenchymal_opacity': ['atelectasis', 'lung_opacity', 'pneumonia', 'consolidation'],
    'focal_lesion': ['lung_lesion', 'granuloma', 'calcification'],
    'pleural': ['pleural_effusion', 'pleural_thickening'],
    'pleural_air': ['pneumothorax'],
    'vascular_congestion': ['edema'],
    'chronic_lung': ['emphysema'],
    'osseous': ['fracture'],
    'diaphragm_mediastinum': ['hernia'],
    'cardiomediastinal': ['cardiomegaly', 'tortuosity_of_the_thoracic_aorta'],
}


def normalize_disease_name(disease_name):
    """将疾病名称标准化为schema中的格式"""
    disease_lower = disease_name.strip().lower()
    for original, schema_name in DISEASE_NAME_MAP.items():
        if disease_lower == original.lower():
            return schema_name
    return disease_name.strip()


def load_concept_counts(csv_path):
    """加载标准化后的概念计数数据"""
    disease_concepts = defaultdict(lambda: defaultdict(int))
    concept_details = {}

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            disease = row['disease']
            concept_key = row['concept_key']
            count = int(row['count'])
            modifiers = row['modifiers']
            anatomical = row['anatomical']

            normalized_disease = normalize_disease_name(disease)
            disease_concepts[normalized_disease][concept_key] += count

            if concept_key not in concept_details:
                concept_details[concept_key] = {
                    'modifiers': modifiers,
                    'anatomical': anatomical,
                }

    return disease_concepts, concept_details


def analyze_by_schema(disease_concepts, concept_details):
    """按照schema规则分析数据"""
    results = {
        'isolated': {},
        'modeling': {},
        'by_family': defaultdict(lambda: defaultdict(int)),
        'stats': {
            'isolated_diseases': set(),
            'modeling_diseases': set(),
        }
    }

    for disease, concepts in disease_concepts.items():
        if disease in ISOLATED_DISEASES:
            results['isolated'][disease] = concepts
            results['stats']['isolated_diseases'].add(disease)
        else:
            results['modeling'][disease] = concepts
            results['stats']['modeling_diseases'].add(disease)

            for family, family_diseases in FAMILY_GROUPS.items():
                if disease in family_diseases:
                    for concept, count in concepts.items():
                        results['by_family'][family][concept] += count
                    break

    return results


def save_results(results, concept_details, output_dir):
    """保存分析结果"""

    # 1. 全局建模概念
    with open(output_dir / 'modeling_concepts_global.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['concept_key', 'modifiers', 'anatomical', 'total_count', 'disease_count'])

        global_concepts = Counter()
        concept_diseases = defaultdict(set)

        for disease, concepts in results['modeling'].items():
            for concept, count in concepts.items():
                global_concepts[concept] += count
                concept_diseases[concept].add(disease)

        for concept, count in sorted(global_concepts.items(), key=lambda x: -x[1]):
            details = concept_details[concept]
            writer.writerow([
                concept, details['modifiers'], details['anatomical'],
                count, len(concept_diseases[concept])
            ])
    print(f"✓ modeling_concepts_global.csv")

    # 2. 按family分组
    with open(output_dir / 'modeling_concepts_by_family.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['family', 'concept_key', 'modifiers', 'anatomical', 'count'])

        for family in sorted(results['by_family'].keys()):
            concepts = results['by_family'][family]
            for concept, count in sorted(concepts.items(), key=lambda x: -x[1]):
                details = concept_details[concept]
                writer.writerow([family, concept, details['modifiers'], details['anatomical'], count])
    print(f"✓ modeling_concepts_by_family.csv")

    # 3. 按疾病分组
    with open(output_dir / 'modeling_concepts_by_disease.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['disease', 'concept_key', 'modifiers', 'anatomical', 'count'])

        for disease in sorted(results['modeling'].keys()):
            concepts = results['modeling'][disease]
            for concept, count in sorted(concepts.items(), key=lambda x: -x[1]):
                details = concept_details[concept]
                writer.writerow([disease, concept, details['modifiers'], details['anatomical'], count])
    print(f"✓ modeling_concepts_by_disease.csv")

    # 4. 隔离疾病摘要
    with open(output_dir / 'isolated_diseases_summary.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['disease', 'concept_count', 'total_phrases', 'top_5_concepts'])

        for disease in sorted(results['isolated'].keys()):
            concepts = results['isolated'][disease]
            total = sum(concepts.values())
            top_concepts = sorted(concepts.items(), key=lambda x: -x[1])[:5]
            top_str = '; '.join([f"{k}({v})" for k, v in top_concepts])
            writer.writerow([disease, len(concepts), total, top_str])
    print(f"✓ isolated_diseases_summary.csv")

    # 5. JSON格式
    json_output = {
        'isolated_diseases': list(results['stats']['isolated_diseases']),
        'modeling_diseases': list(results['stats']['modeling_diseases']),
        'isolated': dict(results['isolated']),
        'modeling': dict(results['modeling']),
        'by_family': dict(results['by_family']),
    }

    with open(output_dir / 'schema_based_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(json_output, f, indent=2, ensure_ascii=False)
    print(f"✓ schema_based_analysis.json")


def print_summary(results, concept_details):
    """打印统计摘要"""
    print("\n" + "=" * 80)
    print("基于 disease_schema.json 的概念统计")
    print("=" * 80)

    isolated = results['isolated']
    modeling = results['modeling']
    by_family = results['by_family']

    print(f"\n数据分类:")
    print(f"  隔离疾病数量: {len(isolated)}")
    print(f"  建模疾病数量: {len(modeling)}")

    print(f"\n[隔离疾病列表]")
    print("-" * 80)
    for disease in sorted(isolated.keys()):
        concepts = isolated[disease]
        total = sum(concepts.values())
        print(f"  {disease:<40} (概念数: {len(concepts):4d}, 总频次: {total:6d})")

    print(f"\n[建模疾病按 family 分组]")
    print("-" * 80)
    for family in sorted(by_family.keys()):
        concepts = by_family[family]
        total_count = sum(concepts.values())
        print(f"\n{family}:")
        print(f"  唯一概念数: {len(concepts)}, 总频次: {total_count}")

        top_concepts = sorted(concepts.items(), key=lambda x: -x[1])[:5]
        print(f"  TOP 5 概念:")
        for concept, count in top_concepts:
            details = concept_details[concept]
            mod_str = details['modifiers'] if details['modifiers'] else '-'
            ana_str = details['anatomical'] if details['anatomical'] else '-'
            print(f"    ({mod_str:<20}, {ana_str:<25}) → {count:5d}")

    global_concepts = Counter()
    for disease, concepts in modeling.items():
        for concept, count in concepts.items():
            global_concepts[concept] += count

    print(f"\n[建模疾病全局 TOP 20 概念]")
    print("-" * 100)
    print(f"{'序号':<4} {'概念键':<30} {'修饰词':<20} {'解剖概念':<20} {'频次':>8}")
    print("-" * 100)

    for i, (concept, count) in enumerate(global_concepts.most_common(20), 1):
        details = concept_details[concept]
        mod_str = details['modifiers'][:20] if details['modifiers'] else '-'
        ana_str = details['anatomical'][:20] if details['anatomical'] else '-'
        print(f"{i:<4} {concept:<30} {mod_str:<20} {ana_str:<20} {count:>8}")


if __name__ == "__main__":
    input_csv = "normalized_concept_counts_by_disease.csv"
    output_dir = Path(".")

    if not Path(input_csv).exists():
        print(f"错误: 文件不存在 - {input_csv}")
        exit(1)

    print("加载标准化概念数据...")
    disease_concepts, concept_details = load_concept_counts(input_csv)
    print(f"加载了 {len(disease_concepts)} 种疾病")

    print("\n按照 disease_schema.json 规则分析...")
    results = analyze_by_schema(disease_concepts, concept_details)

    print("\n保存结果...")
    save_results(results, concept_details, output_dir)

    print_summary(results, concept_details)

    print("\n完成!")
