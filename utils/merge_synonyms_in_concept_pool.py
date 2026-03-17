"""
在全局位置概念池基础上合并同义词
- 修饰词与修饰词之间的合并
- 解剖概念与解剖概念之间的合并
- 建立原始词汇到合并后词汇的映射表
"""

import json
import csv
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Set


# ==================== 同义词合并规则 ====================

# 修饰词同义词组（每组选择第一个作为标准词）
MODIFIER_SYNONYMS = {
    # 左右性变体
    'bilateral': {'both', 'bilateral', 'bilaterally'},

    # 垂直位置 - base相关
    'basal': {'basal', 'basilar', 'bibasilar'},
    'basilar': {'basilar', 'basal', 'bibasilar'},  # 选择 basilar 作为标准（更常用）

    # 垂直位置 - apex相关
    'apical': {'apical', 'apices', 'apex'},

    # 垂直位置 - middle相关
    'mid': {'mid', 'middle', 'medial', 'central'},
    'lower': {'lower', 'inferior', 'lowermost'},
    'upper': {'upper', 'superior', 'uppermost'},

    # 范围相关
    'diffuse': {'diffuse', 'widespread', 'generalized', 'extensive'},
    'focal': {'focal', 'localized', 'isolated'},
    'scattered': {'scattered', 'multifocal', 'patchy'},

    # 严重程度
    'mild': {'mild', 'minimal', 'slight'},
    'severe': {'severe', 'marked', 'massive', 'gross'},

    # 临时/时间相关
    'chronic': {'chronic', 'old', 'long-standing'},
}

# 解剖概念同义词组（每组选择第一个作为标准词）
ANATOMICAL_SYNONYMS = {
    # 肺相关
    'lung': {'lung', 'lungs', 'pulmonary'},
    'lobe': {'lobe', 'lobes'},
    'base': {'base', 'bases', 'basilar', 'basal'},
    'lung base': {'lung base', 'lung bases', 'lung bases bilaterally', 'bases', 'basilar'},

    # 胸膜相关
    'pleural': {'pleural', 'pleura'},
    'pleural space': {
        'pleural space', 'pleural spaces',
        'pleural cavity', 'pleural cavities',
        'pleural', 'pleura'
    },

    # 肋膈角相关
    'costophrenic angle': {
        'costophrenic angle', 'costophrenic angles',
        'costophrenic', 'cp angle', 'cp angles'
    },

    # 心脏相关
    'heart': {'heart', 'cardiac'},
    'cardiac silhouette': {
        'cardiac silhouette', 'cardiomediastinal silhouette',
        'silhouette', 'cardiac border'
    },

    # 主动脉相关
    'aorta': {'aorta', 'aortic'},
    'thoracic aorta': {
        'thoracic aorta', 'descending thoracic aorta',
        'ascending thoracic aorta', 'aorta'
    },
    'aortic arch': {'aortic arch', 'aortic knob'},

    # 膈肌相关
    'hemidiaphragm': {'hemidiaphragm', 'hemidiaphragms', 'diaphragm'},

    # 纵隔相关
    'mediastinum': {'mediastinum', 'mediastinal'},

    # 肺门相关
    'hilum': {'hilum', 'hila', 'hilar'},
    'perihilar': {'perihilar', 'hilar region', 'perihilar region'},

    # 区域相关（泛指）
    'region': {'region', 'regions', 'area', 'areas'},

    # 脊柱相关
    'thoracic spine': {'thoracic spine', 'spine', 'vertebral column'},

    # 肋骨相关
    'rib': {'rib', 'ribs'},

    # 侧胸相关
    'hemithorax': {'hemithorax', 'hemithoraces', 'side'},

    # 胸壁相关
    'chest wall': {'chest wall', 'chest', 'thorax', 'thoracic wall'},

    # 肺尖相关
    'lung apex': {'lung apex', 'apices', 'apex', 'apical'},

    # retrocardiac 相关
    'retrocardiac': {'retrocardiac', 'retrocardiac region', 'retrocardiac area'},

    # 其他常见同义词
    'interstitial': {'interstitial', 'parenchymal', 'parenchyma'},
    'none': {'none', 'normal', 'unremarkable', 'clear'},
}


def build_synonym_mapping():
    """
    构建同义词映射表
    返回: {
        'modifier_mapping': {原始词: 标准词},
        'anatomical_mapping': {原始词: 标准词}
    }
    """
    modifier_mapping = {}
    anatomical_mapping = {}

    # 处理修饰词同义词
    for standard, synonyms in MODIFIER_SYNONYMS.items():
        for syn in synonyms:
            modifier_mapping[syn.lower()] = standard.lower()

    # 处理解剖概念同义词
    for standard, synonyms in ANATOMICAL_SYNONYMS.items():
        for syn in synonyms:
            anatomical_mapping[syn.lower()] = standard.lower()

    return {
        'modifier_mapping': modifier_mapping,
        'anatomical_mapping': anatomical_mapping
    }


def auto_discover_synonyms(concept_pool: dict, min_overlap=0.7):
    """
    自动发现潜在同义词
    基于共现疾病相似度：如果两个概念在相似的疾病中出现，可能是同义词

    Args:
        concept_pool: 概念池字典
        min_overlap: 最小重叠比例（Jaccard相似度阈值）

    Returns:
        发现的同义词组
    """
    discovered_modifier_groups = []
    discovered_anatomical_groups = []

    # 修饰词的同义词发现
    modifiers = concept_pool.get('modifiers', {})
    modifier_diseases = {
        mod: set(info.get('diseases', []))
        for mod, info in modifiers.items()
    }

    for mod1, diseases1 in modifier_diseases.items():
        for mod2, diseases2 in modifier_diseases.items():
            if mod1 >= mod2:  # 避免重复
                continue

            # 计算Jaccard相似度
            intersection = len(diseases1 & diseases2)
            union = len(diseases1 | diseases2)
            jaccard = intersection / union if union > 0 else 0

            if jaccard >= min_overlap:
                # 检查词形相似性（包含关系或词根相同）
                is_similar = (
                    mod1 in mod2 or mod2 in mod1 or
                    mod1[:-1] == mod2[:-1] or  # 去掉s后缀相同
                    len(set(mod1.split()) & set(mod2.split())) > 0  # 有共同词根
                )

                if is_similar:
                    discovered_modifier_groups.append({
                        'group': [mod1, mod2],
                        'jaccard': jaccard,
                        'common_diseases': list(diseases1 & diseases2)
                    })

    # 解剖概念的同义词发现
    anatomicals = concept_pool.get('anatomical_concepts', {})
    anatomical_diseases = {
        ana: set(info.get('diseases', []))
        for ana, info in anatomicals.items()
    }

    for ana1, diseases1 in anatomical_diseases.items():
        for ana2, diseases2 in anatomical_diseases.items():
            if ana1 >= ana2:
                continue

            intersection = len(diseases1 & diseases2)
            union = len(diseases1 | diseases2)
            jaccard = intersection / union if union > 0 else 0

            if jaccard >= min_overlap:
                # 词形相似性检查
                words1 = set(ana1.split())
                words2 = set(ana2.split())

                is_similar = (
                    ana1 in ana2 or ana2 in ana1 or  # 包含关系
                    words1 & words2 or  # 有共同词根
                    (ana1.endswith('s') and ana1[:-1] == ana2) or  # 单复数
                    (ana2.endswith('s') and ana2[:-1] == ana1)
                )

                if is_similar:
                    discovered_anatomical_groups.append({
                        'group': [ana1, ana2],
                        'jaccard': jaccard,
                        'common_diseases': list(diseases1 & diseases2)
                    })

    return {
        'modifier_groups': discovered_modifier_groups,
        'anatomical_groups': discovered_anatomical_groups
    }


def merge_concepts(concept_pool: dict, synonym_mapping: dict):
    """
    使用同义词映射合并概念池

    Returns:
        merged_pool: 合并后的概念池
        merge_stats: 合并统计信息
    """
    modifier_mapping = synonym_mapping['modifier_mapping']
    anatomical_mapping = synonym_mapping['anatomical_mapping']

    merged_pool = {
        'modifiers': defaultdict(lambda: {'frequency': 0, 'disease_count': 0, 'diseases': set(), 'source_terms': set()}),
        'anatomical_concepts': defaultdict(lambda: {'frequency': 0, 'disease_count': 0, 'diseases': set(), 'source_terms': set()}),
        'special_concepts': {}
    }

    merge_stats = {
        'modifier_merges': defaultdict(list),
        'anatomical_merges': defaultdict(list),
        'merged_modifier_count': 0,
        'merged_anatomical_count': 0
    }

    # 合并修饰词
    for mod, info in concept_pool.get('modifiers', {}).items():
        # 查找标准词
        standard = modifier_mapping.get(mod.lower(), mod)

        # 合并信息
        merged_pool['modifiers'][standard]['frequency'] += info['frequency']
        merged_pool['modifiers'][standard]['diseases'].update(info.get('diseases', []))
        merged_pool['modifiers'][standard]['source_terms'].add(mod)

        # 记录合并
        if standard != mod:
            merge_stats['modifier_merges'][standard].append(mod)
            merge_stats['merged_modifier_count'] += 1

    # 合并解剖概念
    for ana, info in concept_pool.get('anatomical_concepts', {}).items():
        standard = anatomical_mapping.get(ana.lower(), ana)

        merged_pool['anatomical_concepts'][standard]['frequency'] += info['frequency']
        merged_pool['anatomical_concepts'][standard]['diseases'].update(info.get('diseases', []))
        merged_pool['anatomical_concepts'][standard]['source_terms'].add(ana)

        if standard != ana:
            merge_stats['anatomical_merges'][standard].append(ana)
            merge_stats['merged_anatomical_count'] += 1

    # 处理特殊概念
    merged_pool['special_concepts'] = concept_pool.get('special_concepts', {})

    # 计算疾病数量
    for category in ['modifiers', 'anatomical_concepts']:
        for concept, info in merged_pool[category].items():
            info['disease_count'] = len(info['diseases'])
            info['diseases'] = sorted(info['diseases'])
            info['source_terms'] = sorted(info['source_terms'])

    # 转换为普通字典
    merged_pool['modifiers'] = dict(merged_pool['modifiers'])
    merged_pool['anatomical_concepts'] = dict(merged_pool['anatomical_concepts'])

    return merged_pool, merge_stats


def save_merged_results(merged_pool, merge_stats, synonym_mapping, discovered_synonyms, output_dir):
    """保存合并结果"""

    # 1. 保存合并后的概念池
    with open(output_dir / 'location_concept_pool_merged.json', 'w', encoding='utf-8') as f:
        json.dump(merged_pool, f, indent=2, ensure_ascii=False)
    print(f"✓ 合并后的概念池已保存: location_concept_pool_merged.json")

    # 2. 保存映射表（原始 -> 标准）
    with open(output_dir / 'synonym_mapping.json', 'w', encoding='utf-8') as f:
        json.dump(synonym_mapping, f, indent=2, ensure_ascii=False)
    print(f"✓ 同义词映射表已保存: synonym_mapping.json")

    # 3. 保存合并统计信息
    with open(output_dir / 'merge_stats.json', 'w', encoding='utf-8') as f:
        # 转换set为list以便JSON序列化
        stats_to_save = dict(merge_stats)
        json.dump(stats_to_save, f, indent=2, ensure_ascii=False)
    print(f"✓ 合并统计已保存: merge_stats.json")

    # 4. 保存CSV格式的映射表
    with open(output_dir / 'synonym_mapping.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['category', 'original_term', 'standard_term', 'action'])

        # 修饰词映射
        for original, standard in sorted(synonym_mapping['modifier_mapping'].items()):
            if original != standard:
                writer.writerow(['modifier', original, standard, 'merged'])

        # 解剖概念映射
        for original, standard in sorted(synonym_mapping['anatomical_mapping'].items()):
            if original != standard:
                writer.writerow(['anatomical', original, standard, 'merged'])
    print(f"✓ CSV映射表已保存: synonym_mapping.csv")

    # 5. 保存自动发现的同义词组
    with open(output_dir / 'discovered_synonyms.json', 'w', encoding='utf-8') as f:
        json.dump(discovered_synonyms, f, indent=2, ensure_ascii=False)
    print(f"✓ 自动发现的同义词组已保存: discovered_synonyms.json")

    # 6. 保存合并后的概念清单CSV
    with open(output_dir / 'location_concepts_merged.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['category', 'standard_term', 'frequency', 'disease_count', 'source_terms', 'diseases'])

        for concept, info in sorted(merged_pool['modifiers'].items(), key=lambda x: -x[1]['frequency']):
            source_str = '; '.join(info['source_terms'])
            diseases_str = '; '.join(info['diseases'])
            writer.writerow(['modifier', concept, info['frequency'], info['disease_count'], source_str, diseases_str])

        for concept, info in sorted(merged_pool['anatomical_concepts'].items(), key=lambda x: -x[1]['frequency']):
            source_str = '; '.join(info['source_terms'])
            diseases_str = '; '.join(info['diseases'])
            writer.writerow(['anatomical', concept, info['frequency'], info['disease_count'], source_str, diseases_str])
    print(f"✓ 合并后的概念清单已保存: location_concepts_merged.csv")


def print_merge_summary(merged_pool, merge_stats, discovered_synonyms):
    """打印合并摘要"""

    print("\n" + "=" * 80)
    print("同义词合并摘要")
    print("=" * 80)

    original_modifiers = len(merge_stats['modifier_merges']) + len([k for k in merged_pool['modifiers'] if len(merged_pool['modifiers'][k]['source_terms']) == 1])
    original_anatomicals = len(merge_stats['anatomical_merges']) + len([k for k in merged_pool['anatomical_concepts'] if len(merged_pool['anatomical_concepts'][k]['source_terms']) == 1])

    print(f"\n修饰词:")
    print(f"  原始数量: {original_modifiers}")
    print(f"  合并后数量: {len(merged_pool['modifiers'])}")
    print(f"  合并操作数: {merge_stats['merged_modifier_count']}")

    print(f"\n解剖概念:")
    print(f"  原始数量: {original_anatomicals}")
    print(f"  合并后数量: {len(merged_pool['anatomical_concepts'])}")
    print(f"  合并操作数: {merge_stats['merged_anatomical_count']}")

    # 显示合并示例
    print("\n[修饰词合并示例]")
    print("-" * 80)
    for standard, sources in list(merge_stats['modifier_merges'].items())[:10]:
        print(f"  {standard} ← {', '.join(sources)}")

    print("\n[解剖概念合并示例]")
    print("-" * 80)
    for standard, sources in list(merge_stats['anatomical_merges'].items())[:15]:
        print(f"  {standard} ← {', '.join(sources)}")

    # 自动发现的同义词
    print("\n[自动发现的潜在同义词组]")
    print("-" * 80)

    mod_groups = discovered_synonyms['modifier_groups']
    if mod_groups:
        print(f"\n修饰词同义词组 ({len(mod_groups)} 个):")
        for group in sorted(mod_groups, key=lambda x: -x['jaccard'])[:10]:
            print(f"  {group['group'][0]} ≈ {group['group'][1]} (相似度: {group['jaccard']:.2f})")

    ana_groups = discovered_synonyms['anatomical_groups']
    if ana_groups:
        print(f"\n解剖概念同义词组 ({len(ana_groups)} 个):")
        for group in sorted(ana_groups, key=lambda x: -x['jaccard'])[:15]:
            print(f"  {group['group'][0]} ≈ {group['group'][1]} (相似度: {group['jaccard']:.2f})")

    # 合并后的TOP概念
    print("\n[合并后修饰词 TOP 15]")
    print("-" * 80)
    for i, (mod, info) in enumerate(sorted(merged_pool['modifiers'].items(), key=lambda x: -x[1]['frequency'])[:15], 1):
        source_count = len(info['source_terms'])
        source_note = f" (合并了 {source_count} 个词)" if source_count > 1 else ""
        print(f"  {i:2d}. {mod:20s} (频次: {info['frequency']:5d}, 疾病: {info['disease_count']:2d}){source_note}")

    print("\n[合并后解剖概念 TOP 20]")
    print("-" * 80)
    for i, (ana, info) in enumerate(sorted(merged_pool['anatomical_concepts'].items(), key=lambda x: -x[1]['frequency'])[:20], 1):
        source_count = len(info['source_terms'])
        source_note = f" (合并了 {source_count} 个词)" if source_count > 1 else ""
        print(f"  {i:2d}. {ana:30s} (频次: {info['frequency']:5d}, 疾病: {info['disease_count']:2d}){source_note}")


if __name__ == "__main__":
    input_json = "location_concept_pool_v2.json"
    output_dir = Path(".")

    if not Path(input_json).exists():
        print(f"错误: 文件不存在 - {input_json}")
        print("请先运行 build_location_concept_pool_v2.py 生成概念池")
        exit(1)

    # 加载概念池
    print("加载概念池...")
    with open(input_json, 'r', encoding='utf-8') as f:
        concept_pool = json.load(f)

    print(f"  修饰词: {len(concept_pool.get('modifiers', {}))}")
    print(f"  解剖概念: {len(concept_pool.get('anatomical_concepts', {}))}")

    # 1. 构建同义词映射
    print("\n构建同义词映射...")
    synonym_mapping = build_synonym_mapping()

    print(f"  修饰词映射: {len(synonym_mapping['modifier_mapping'])} 条")
    print(f"  解剖概念映射: {len(synonym_mapping['anatomical_mapping'])} 条")

    # 2. 自动发现潜在同义词
    print("\n自动发现潜在同义词...")
    discovered_synonyms = auto_discover_synonyms(concept_pool, min_overlap=0.6)

    print(f"  发现修饰词同义词组: {len(discovered_synonyms['modifier_groups'])}")
    print(f"  发现解剖概念同义词组: {len(discovered_synonyms['anatomical_groups'])}")

    # 3. 执行合并
    print("\n执行同义词合并...")
    merged_pool, merge_stats = merge_concepts(concept_pool, synonym_mapping)

    # 4. 保存结果
    print("\n保存结果...")
    save_merged_results(merged_pool, merge_stats, synonym_mapping, discovered_synonyms, output_dir)

    # 5. 打印摘要
    print_merge_summary(merged_pool, merge_stats, discovered_synonyms)

    print("\n完成!")
