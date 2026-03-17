"""
构建全局位置概念池
通过分析短语频率和模式，自动提取：
1. 解剖位置概念 (anatomy concepts): 如 heart, pleural space, apex, base 等
2. 修饰词 (modifiers): 如 left, right, bilateral, diffuse 等
"""

import json
import csv
from collections import defaultdict, Counter
from pathlib import Path
import re
from typing import Set, Dict, Tuple

# spaCy可选导入
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
    HAS_SPACY = True
except (ImportError, OSError):
    HAS_SPACY = False


def load_phrase_counts(csv_path):
    """加载疾病-短语频次数据"""
    phrases_by_disease = defaultdict(dict)
    all_phrases = Counter()

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            disease = row['disease']
            phrase = row['phrase']
            count = int(row['count'])
            phrases_by_disease[disease][phrase] = count
            all_phrases[phrase] += count

    return phrases_by_disease, all_phrases


def extract_word_patterns(phrases: Counter, min_freq=50):
    """
    提取单词级别的模式
    返回: 单词频率, 常见二元组, 常见三元组
    """
    # 单个词的频率（小写化）
    single_words = Counter()
    # 二元组
    bigrams = Counter()
    # 三元组
    trigrams = Counter()

    for phrase, total_count in phrases.items():
        phrase_lower = phrase.lower()
        words = phrase_lower.split()

        # 单词统计
        for word in words:
            if len(word) > 1:  # 过滤单字母
                single_words[word] += total_count

        # 二元组
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            bigrams[bigram] += total_count

        # 三元组
        for i in range(len(words) - 2):
            trigram = f"{words[i]} {words[i+1]} {words[i+2]}"
            trigrams[trigram] += total_count

    return single_words, bigrams, trigrams


def is_directional_word(word):
    """判断是否为方向性修饰词"""
    directional = {
        'left', 'right', 'bilateral', 'bilateral', 'both',
        'mid', 'middle', 'central', 'median', 'medial',
        'superior', 'inferior', 'upper', 'lower', 'uppermost', 'lowermost',
        'anterior', 'posterior', 'dorsal', 'ventral',
        'lateral', 'medial', 'proximal', 'distal',
        'internal', 'external', 'inner', 'outer',
        'ipsilateral', 'contralateral',
        'diffuse', 'focal', 'multifocal', 'scattered', 'patchy',
        'generalized', 'localized', 'extensive', 'mild', 'moderate', 'severe'
    }
    return word.lower() in directional


def is_pure_anatomical(word):
    """判断是否为纯解剖词（排除方向和数量词）"""
    # 方向/修饰词（排除）
    modifiers = {
        'left', 'right', 'bilateral', 'both', 'mid', 'middle', 'central',
        'upper', 'lower', 'superior', 'inferior', 'anterior', 'posterior',
        'lateral', 'medial', 'diffuse', 'focal', 'multifocal', 'scattered',
        'no', 'none', 'normal', 'unremarkable', 'clear', 'stable',
        'mild', 'moderate', 'severe', 'small', 'large', 'tiny',
        'new', 'old', 'chronic', 'acute', 'progressive',
        'single', 'multiple', 'several', 'numerous',
        'possible', 'suggestive', 'consistent', 'compatible',
        'within', 'without', 'with', 'without', 'and', 'or', 'of', 'in', 'at', 'to', 'the', 'a', 'an'
    }

    word_lower = word.lower().strip('.,')
    return word_lower not in modifiers and len(word_lower) > 1


def analyze_positional_variants(phrases: Counter):
    """
    分析位置变体模式
    例如: "left pleural space", "right pleural space" -> "pleural space" 是概念, "left/right" 是修饰
    """
    # 收集有左右变体的短语模式
    left_right_pairs = []

    phrase_list = list(phrases.items())

    for (phrase1, count1), (phrase2, count2) in zip(phrase_list, phrase_list[1:]):
        p1_lower = phrase1.lower()
        p2_lower = phrase2.lower()

        # 检查是否为左右变体
        if p1_lower.startswith('left ') and p2_lower.startswith('right '):
            rest1 = p1_lower[5:]  # 去掉 "left "
            rest2 = p2_lower[6:]  # 去掉 "right "
            if rest1 == rest2:
                left_right_pairs.append((rest1, count1 + count2))

        elif p1_lower.startswith('right ') and p2_lower.startswith('left '):
            rest1 = p1_lower[6:]
            rest2 = p2_lower[5:]
            if rest1 == rest2:
                left_right_pairs.append((rest1, count1 + count2))

    return left_right_pairs


def extract_anatomical_roots(phrases: Counter):
    """
    提取解剖词根
    通过分析短语中共现的高频词
    """
    anatomical_candidates = Counter()

    for phrase, count in phrases.items():
        # 分词并过滤
        words = phrase.split()
        for word in words:
            if is_pure_anatomical(word) and len(word) > 2:
                anatomical_candidates[word.lower()] += count

    return anatomical_candidates


def build_concept_pool(phrases_by_disease, all_phrases, output_dir):
    """
    构建概念池
    """
    print("=" * 60)
    print("构建全局位置概念池")
    print("=" * 60)

    # 1. 提取单词级模式
    print("\n[步骤1] 提取单词级模式...")
    single_words, bigrams, trigrams = extract_word_patterns(all_phrases)

    print(f"  - 独特单词数: {len(single_words)}")
    print(f"  - 独特二元组数: {len(bigrams)}")
    print(f"  - 独特三元组数: {len(trigrams)}")

    # 2. 分析左右变体（识别被修饰的概念）
    print("\n[步骤2] 分析左右位置变体...")
    left_right_variants = analyze_positional_variants(all_phrases)
    print(f"  - 发现 {len(left_right_variants)} 个有左右变体的解剖位置")

    # 3. 提取解剖词根候选
    print("\n[步骤3] 提取解剖词根候选...")
    anatomical_roots = extract_anatomical_roots(all_phrases)

    # 4. 构建修饰词集合
    print("\n[步骤4] 识别修饰词...")

    # 方法A: 明确的方向/范围词
    modifiers_explicit = set()
    for word, count in single_words.items():
        if is_directional_word(word):
            modifiers_explicit.add(word)

    # 方法B: 经常出现在短语开头的词（可能是修饰）
    prefix_words = Counter()
    for phrase, count in all_phrases.items():
        first_word = phrase.split()[0].lower()
        if len(first_word) > 1:
            prefix_words[first_word] += count

    # 5. 构建最终概念池
    print("\n[步骤5] 构建概念池...")

    # 概念池结构
    concept_pool = {
        'anatomical_concepts': {},  # 解剖概念
        'modifiers': {},            # 修饰词
        'compound_locations': {},   # 复合位置（从左右变体提取）
    }

    # 5.1 填充解剖概念（高频解剖词 + 多词组合）
    high_freq_threshold = 100
    for word, count in anatomical_roots.most_common():
        if count >= high_freq_threshold and word not in modifiers_explicit:
            concept_pool['anatomical_concepts'][word] = {
                'type': 'single',
                'frequency': count,
                'examples': []
            }

    # 添加高频二元组和三元组作为复合概念
    for bigram, count in bigrams.most_common(200):
        if count >= high_freq_threshold:
            words = bigram.split()
            # 排除明显是修饰+结构的组合
            if not (is_directional_word(words[0]) or is_directional_word(words[1])):
                concept_pool['anatomical_concepts'][bigram] = {
                    'type': 'bigram',
                    'frequency': count,
                    'examples': []
                }

    for trigram, count in trigrams.most_common(100):
        if count >= 200:  # 三元组需要更高频率
            concept_pool['anatomical_concepts'][trigram] = {
                'type': 'trigram',
                'frequency': count,
                'examples': []
            }

    # 5.2 填充修饰词
    for modifier in sorted(modifiers_explicit):
        concept_pool['modifiers'][modifier] = {
            'frequency': single_words[modifier],
            'category': categorize_modifier(modifier)
        }

    # 5.3 填充复合位置（从左右变体）
    for location, total_count in left_right_variants:
        if total_count >= 20:  # 至少20次出现
            concept_pool['compound_locations'][location] = {
                'frequency': total_count,
                'has_left_right_variants': True
            }

    # 添加示例短语
    print("\n[步骤6] 为概念添加示例短语...")
    concept_pool = add_examples_to_concepts(concept_pool, all_phrases)

    # 输出统计
    print("\n" + "=" * 60)
    print("概念池统计:")
    print("=" * 60)
    print(f"解剖概念数: {len(concept_pool['anatomical_concepts'])}")
    print(f"修饰词数: {len(concept_pool['modifiers'])}")
    print(f"复合位置数: {len(concept_pool['compound_locations'])}")

    # 保存结果
    output_path = Path(output_dir) / "location_concept_pool.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(concept_pool, f, indent=2, ensure_ascii=False)

    print(f"\n概念池已保存到: {output_path}")

    # 生成CSV格式的概念清单
    save_concept_csv(concept_pool, Path(output_dir) / "location_concepts.csv")

    return concept_pool


def categorize_modifier(modifier):
    """给修饰词分类"""
    modifier = modifier.lower()

    categories = {
        'laterality': ['left', 'right', 'bilateral', 'both', 'ipsilateral', 'contralateral'],
        'vertical': ['upper', 'lower', 'superior', 'inferior', 'uppermost', 'lowermost', 'mid', 'middle'],
        'horizontal': ['anterior', 'posterior', 'lateral', 'medial', 'central', 'median'],
        'distribution': ['diffuse', 'focal', 'multifocal', 'scattered', 'patchy', 'generalized', 'localized', 'extensive'],
        'severity': ['mild', 'moderate', 'severe', 'minimal', 'marked'],
        'size': ['small', 'large', 'tiny', 'massive'],
        'temporality': ['acute', 'chronic', 'new', 'old', 'progressive', 'stable', 'resolved']
    }

    for category, words in categories.items():
        if modifier in words:
            return category

    return 'other'


def add_examples_to_concepts(concept_pool, all_phrases):
    """为每个概念添加示例短语"""
    # 为解剖概念添加示例
    for concept, info in concept_pool['anatomical_concepts'].items():
        concept_lower = concept.lower()
        examples = []

        for phrase, count in all_phrases.items():
            if concept_lower in phrase.lower():
                examples.append(f"{phrase} ({count})")
                if len(examples) >= 3:
                    break

        info['examples'] = examples

    # 为复合位置添加示例
    for location, info in concept_pool['compound_locations'].items():
        examples = []
        for phrase, count in all_phrases.items():
            if location.lower() in phrase.lower():
                examples.append(f"{phrase} ({count})")
                if len(examples) >= 3:
                    break
        info['examples'] = examples

    return concept_pool


def save_concept_csv(concept_pool, output_path):
    """保存概念池为CSV格式"""
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['category', 'concept', 'frequency', 'details'])

        # 解剖概念
        for concept, info in sorted(concept_pool['anatomical_concepts'].items(),
                                    key=lambda x: x[1]['frequency'], reverse=True):
            writer.writerow([
                'anatomical_concept',
                concept,
                info['frequency'],
                f"type={info.get('type', 'N/A')}"
            ])

        # 修饰词
        for modifier, info in sorted(concept_pool['modifiers'].items(),
                                     key=lambda x: x[1]['frequency'], reverse=True):
            writer.writerow([
                'modifier',
                modifier,
                info['frequency'],
                f"category={info['category']}"
            ])

        # 复合位置
        for location, info in sorted(concept_pool['compound_locations'].items(),
                                     key=lambda x: x[1]['frequency'], reverse=True):
            writer.writerow([
                'compound_location',
                location,
                info['frequency'],
                "has_left_right_variants=True"
            ])

    print(f"CSV格式概念清单已保存到: {output_path}")


def analyze_and_visualize(concept_pool):
    """分析和可视化概念池"""
    print("\n" + "=" * 60)
    print("概念池详细分析")
    print("=" * 60)

    # 1. 解剖概念 TOP 30
    print("\n[解剖概念 TOP 30]")
    print("-" * 60)
    sorted_concepts = sorted(concept_pool['anatomical_concepts'].items(),
                            key=lambda x: x[1]['frequency'], reverse=True)
    for i, (concept, info) in enumerate(sorted_concepts[:30], 1):
        print(f"{i:2d}. {concept:30s} (频次: {info['frequency']:5d}, 类型: {info.get('type', 'N/A')})")

    # 2. 修饰词分类统计
    print("\n[修饰词分类]")
    print("-" * 60)
    modifier_categories = defaultdict(list)
    for modifier, info in concept_pool['modifiers'].items():
        modifier_categories[info['category']].append((modifier, info['frequency']))

    for category in sorted(modifier_categories.keys()):
        print(f"\n{category.upper()}:")
        for modifier, freq in sorted(modifier_categories[category], key=lambda x: -x[1]):
            print(f"  - {modifier:20s} ({freq:5d})")

    # 3. 复合位置 TOP 20
    print("\n[复合位置 TOP 20]")
    print("-" * 60)
    sorted_locations = sorted(concept_pool['compound_locations'].items(),
                             key=lambda x: x[1]['frequency'], reverse=True)
    for i, (location, info) in enumerate(sorted_locations[:20], 1):
        print(f"{i:2d}. {location:40s} (频次: {info['frequency']:5d})")


if __name__ == "__main__":
    # 输入输出路径
    input_csv = "disease_phrase_counts.csv"
    output_dir = "."

    # 检查输入文件
    if not Path(input_csv).exists():
        print(f"错误: 文件不存在 - {input_csv}")
        print("请先运行 extract_disease_phrase_counts.py 生成短语统计文件")
        exit(1)

    # 加载数据
    print("加载短语统计数据...")
    phrases_by_disease, all_phrases = load_phrase_counts(input_csv)

    print(f"加载了 {len(phrases_by_disease)} 种疾病")
    print(f"总共 {len(all_phrases)} 种独特短语")

    # 构建概念池
    concept_pool = build_concept_pool(phrases_by_disease, all_phrases, output_dir)

    # 分析和可视化
    analyze_and_visualize(concept_pool)

    print("\n完成!")
