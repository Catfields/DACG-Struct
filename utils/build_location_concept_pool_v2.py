"""
构建全局位置概念池 - 版本2
对每个短语进行语义拆解，分解为：修饰词 + 解剖概念

例如：
- "bilateral" → [修饰词: bilateral]
- "left pleural space" → [修饰词: left] + [解剖概念: pleural space]
- "bilateral costophrenic angles" → [修饰词: bilateral] + [解剖概念: costophrenic angles]
- "bibasilar" → [特殊概念: bibasilar] 或 [修饰词: bilateral] + [解剖概念: basilar]
"""

import json
import csv
from collections import defaultdict, Counter
from pathlib import Path


# ==================== 预定义的知识库 ====================

# 常见的修饰词（方向、范围、分布等）
KNOWN_MODIFIERS = {
    # 左右性
    'left', 'right', 'bilateral', 'both', 'unilateral', 'ipsilateral', 'contralateral',

    # 垂直位置
    'upper', 'lower', 'superior', 'inferior', 'uppermost', 'lowermost',
    'mid', 'middle', 'central', 'median',

    # 水平位置
    'anterior', 'posterior', 'lateral', 'medial', 'dorsal', 'ventral',
    'inner', 'outer', 'internal', 'external', 'proximal', 'distal',

    # 范围/分布
    'diffuse', 'focal', 'multifocal', 'scattered', 'patchy', 'generalized',
    'localized', 'extensive', 'widespread', 'isolated',

    # 严重程度
    'mild', 'moderate', 'severe', 'minimal', 'marked', 'slight',

    # 大小
    'small', 'large', 'tiny', 'massive', 'gross',

    # 时间性
    'acute', 'chronic', 'new', 'old', 'progressive', 'stable', 'resolved',
}

# 常见的解剖相关前缀（这些词虽然可能是解剖词，但经常作修饰用）
# 注意：这些词后面紧跟解剖词时，会被视为修饰词
ANATOMICAL_PREFIX_MODIFIERS = {
    'apical', 'basal', 'basilar', 'hilar', 'perihilar', 'suprahilar', 'infrahilar',
    'retrocardiac', 'subcarinal', 'paratracheal', 'paraspinal',
    'cardiophrenic', 'costophrenic',
}

# 特殊组合词映射（不可拆分的复合概念）
SPECIAL_CONCEPT_MAPPINGS = {
    'bibasilar': {'modifiers': ['bilateral'], 'anatomical': 'basilar', 'is_special': True},
    'bilateralbasilar': {'modifiers': ['bilateral'], 'anatomical': 'basilar', 'is_special': True},
    'bicostophrenic': {'modifiers': ['bilateral'], 'anatomical': 'costophrenic', 'is_special': True},
}

# 复合解剖概念（这些多词组合应该整体识别为解剖概念，不可拆分）
# 例如: "costophrenic angle" 应该作为一个整体，而不是 "costophrenic"(修饰) + "angle"(解剖)
COMPOUND_ANATOMICAL_CONCEPTS = {
    # 胸腔/肺相关
    'pleural space', 'pleural spaces', 'pleural cavity', 'pleural cavities',
    'costophrenic angle', 'costophrenic angles',
    'cardiophrenic angle', 'cardiophrenic angles',
    'lung base', 'lung bases', 'lung zone', 'lung zones',
    'lower lobe', 'lower lobes', 'upper lobe', 'upper lobes',
    'left lower lobe', 'right lower lobe', 'left upper lobe', 'right upper lobe',
    'middle lobe', 'lingula',
    'cardiac silhouette', 'cardiomediastinal silhouette',
    'aortic arch', 'aortic knob', 'ascending aorta', 'descending aorta',
    'thoracic aorta', 'thoracic spine',
    'chest wall', 'chest tube', 'chest tubes',

    # 区域相关
    'hilum', 'hila', 'hilar region', 'perihilar region',
    'retrocardiac region', 'suprahilar region', 'infrahilar region',

    # 其他
    'gastric bubble', 'nasogastric tube', 'orogastric tube',
    'central line', 'picc line', 'dialysis catheter',
}

# 常见的解剖概念词干（用于识别解剖部分）
ANATOMICAL_KEYWORDS = {
    # 呼吸系统
    'lung', 'lungs', 'lobe', 'lobes', 'lingula', 'pleural', 'pleura',
    'pulmonary', 'parenchymal', 'parenchyma', 'interstitial',

    # 胸腔结构
    'chest', 'thoracic', 'thorax', 'hemithorax', 'mediastinal', 'mediastinum',
    'cardiac', 'cardiomediastinal', 'cardiophrenic', 'costophrenic',
    'hilar', 'hilum', 'perihilar', 'suprahilar', 'infrahilar',
    'retrocardiac', 'subcarinal', 'paratracheal', 'paraspinal',

    # 血管
    'aorta', 'aortic', 'vascular', 'pulmonary', 'artery', 'vein',

    # 骨骼
    'rib', 'ribs', 'clavicle', 'sternum', 'spine', 'vertebral', 'scapula',
    'humerus', 'acromioclavicular',

    # 横膈
    'diaphragm', 'hemidiaphragm',

    # 心脏
    'heart', 'cardiac', 'atrial', 'ventricular',

    # 导管/设备
    'tube', 'catheter', 'line', 'port', 'device', 'wire', 'electrode',
    'pacemaker', 'defibrillator', 'stent', 'clip', 'staple',

    # 通用位置词
    'space', 'region', 'area', 'zone', 'field', 'base', 'bases',
    'angle', 'angles', 'apex', 'apices', 'margin', 'border',
    'contour', 'silhouette', 'shadow', 'opacity', 'densities',

    # 手术相关
    'sternotomy', 'thoracotomy', 'chest', 'tube', 'drain',
}


# ==================== 短语拆解算法 ====================

class PhraseDecomposer:
    """短语拆解器：将短语分解为修饰词和解剖概念"""

    def __init__(self):
        # 统计信息
        self.stats = defaultdict(int)
        # 特殊概念库（不可拆分的复合词）
        self.special_concepts = set()

    def decompose(self, phrase):
        """
        拆解短语为修饰词和解剖概念

        返回: {
            'modifiers': [修饰词列表],
            'anatomical': 解剖概念字符串,
            'is_special': 是否为特殊概念
        }
        """
        result = {
            'modifiers': [],
            'anatomical': '',
            'is_special': False,
            'original': phrase
        }

        phrase = phrase.strip()
        if not phrase:
            return result

        # 检查是否为纯修饰词
        if phrase.lower() in KNOWN_MODIFIERS:
            result['modifiers'] = [phrase.lower()]
            result['anatomical'] = ''
            result['is_special'] = False
            self.stats['pure_modifier'] += 1
            return result

        # 检查特殊组合词
        special = self._check_special_concept(phrase)
        if special:
            result['modifiers'] = special['modifiers']
            result['anatomical'] = special['anatomical']
            result['is_special'] = special['is_special']
            self.stats['special_concept'] += 1
            return result

        # 常规拆解
        return self._regular_decompose(phrase)

    def _check_special_concept(self, phrase):
        """检查是否为特殊概念（不可拆分或需要特殊处理）"""
        phrase_lower = phrase.lower()

        # 特殊组合词映射（使用全局定义）
        if phrase_lower in SPECIAL_CONCEPT_MAPPINGS:
            return SPECIAL_CONCEPT_MAPPINGS[phrase_lower]

        # 检查是否以 known modifiers 开头，但后面是解剖概念
        # 这种情况按常规处理，不算特殊
        return None

    def _regular_decompose(self, phrase):
        """常规短语拆解"""
        result = {
            'modifiers': [],
            'anatomical': '',
            'is_special': False,
            'original': phrase
        }

        phrase_lower = phrase.lower()
        words = phrase.split()
        i = 0
        n = len(words)

        # 步骤1: 从前向后提取纯修饰词（不包括解剖前缀修饰词）
        while i < n:
            word = words[i].lower()
            if word in KNOWN_MODIFIERS:
                result['modifiers'].append(word)
                i += 1
            else:
                break

        # 步骤2: 检查剩余部分是否包含复合解剖概念
        remaining_words = words[i:]
        remaining_phrase = ' '.join(remaining_words).lower()

        # 尝试匹配复合解剖概念
        matched_compound = None
        matched_length = 0

        for compound in sorted(COMPOUND_ANATOMICAL_CONCEPTS, key=len, reverse=True):
            if remaining_phrase.startswith(compound.lower()):
                # 检查匹配的是否完整单词（避免部分匹配）
                compound_words = compound.split()
                if len(remaining_words) >= len(compound_words):
                    matched_compound = compound
                    matched_length = len(compound_words)
                    break

        if matched_compound:
            # 有复合解剖概念
            result['anatomical'] = matched_compound
            # 复合概念之前的词已经作为修饰词提取了
            # 复合概念之后可能还有词
            if matched_length < len(remaining_words):
                remaining_after = remaining_words[matched_length:]
                # 检查剩余的词是否为修饰词
                for word in remaining_after:
                    word_lower = word.lower()
                    if word_lower in KNOWN_MODIFIERS or word_lower in ANATOMICAL_PREFIX_MODIFIERS:
                        result['modifiers'].append(word_lower)
                    # 也可以追加到解剖概念后面
                    elif result['anatomical']:
                        result['anatomical'] += ' ' + word
        else:
            # 没有复合解剖概念，使用常规方法
            # 从当前位置开始，提取解剖前缀修饰词
            while i < n:
                word = words[i].lower()
                if word in ANATOMICAL_PREFIX_MODIFIERS:
                    result['modifiers'].append(word)
                    i += 1
                else:
                    break

            # 剩余部分作为解剖概念
            if i < n:
                anatomical_words = words[i:]
                anatomical = ' '.join(anatomical_words)
                result['anatomical'] = anatomical
            elif result['modifiers']:
                # 整个短语都是修饰词
                pass
            else:
                # 没有识别出修饰词，整个短语作为解剖概念
                result['anatomical'] = phrase

        # 统计
        if not result['anatomical'] and result['modifiers']:
            self.stats['pure_modifier'] += 1
        elif result['anatomical'] and not result['modifiers']:
            self.stats['pure_anatomical'] += 1
        elif result['anatomical'] and result['modifiers']:
            self.stats['mixed'] += 1
        else:
            # 都没有，整个短语作为特殊概念
            result['anatomical'] = phrase
            result['is_special'] = True
            self.stats['fallback_special'] += 1

        return result


def load_disease_phrases(csv_path):
    """加载疾病-短语数据"""
    disease_phrases = defaultdict(list)

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            disease = row['disease']
            phrase = row['phrase']
            count = int(row['count'])
            disease_phrases[disease].append((phrase, count))

    return disease_phrases


def build_global_concept_pool(disease_phrases):
    """
    构建全局概念池
    通过分析所有短语的拆解结果，提取：
    1. 全局修饰词集合
    2. 全局解剖概念集合
    3. 特殊概念集合
    """
    decomposer = PhraseDecomposer()

    # 统计概念出现情况
    modifier_usage = Counter()  # 修饰词使用频次
    anatomical_usage = Counter()  # 解剖概念使用频次
    special_concepts = Counter()  # 特殊概念使用频次

    # 记录每个概念出现在哪些疾病中
    modifier_to_diseases = defaultdict(set)
    anatomical_to_diseases = defaultdict(set)
    special_to_diseases = defaultdict(set)

    # 按疾病处理
    for disease, phrases in disease_phrases.items():
        for phrase, count in phrases:
            result = decomposer.decompose(phrase)

            # 统计修饰词
            for mod in result['modifiers']:
                modifier_usage[mod] += count
                modifier_to_diseases[mod].add(disease)

            # 统计解剖概念
            if result['anatomical']:
                anatomical_usage[result['anatomical']] += count
                anatomical_to_diseases[result['anatomical']].add(disease)

            # 统计特殊概念
            if result['is_special']:
                special_key = result['anatomical'] or '_'.join(result['modifiers'])
                special_concepts[special_key] += count
                special_to_diseases[special_key].add(disease)

    # 构建概念池
    concept_pool = {
        'modifiers': {},
        'anatomical_concepts': {},
        'special_concepts': {},
        'stats': dict(decomposer.stats)
    }

    # 填充修饰词（按频次排序，只保留出现>=10次的）
    for mod, count in modifier_usage.most_common():
        if count >= 10:
            concept_pool['modifiers'][mod] = {
                'frequency': count,
                'disease_count': len(modifier_to_diseases[mod]),
                'diseases': sorted(modifier_to_diseases[mod])
            }

    # 填充解剖概念（按频次排序，只保留出现>=10次的）
    for ana, count in anatomical_usage.most_common():
        if count >= 10:
            concept_pool['anatomical_concepts'][ana] = {
                'frequency': count,
                'disease_count': len(anatomical_to_diseases[ana]),
                'diseases': sorted(anatomical_to_diseases[ana])
            }

    # 填充特殊概念
    for sp, count in special_concepts.most_common():
        if count >= 5:
            concept_pool['special_concepts'][sp] = {
                'frequency': count,
                'disease_count': len(special_to_diseases[sp]),
                'diseases': sorted(special_to_diseases[sp])
            }

    return concept_pool


def save_concept_pool(concept_pool, output_json, output_csv):
    """保存概念池"""
    # 保存JSON格式
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(concept_pool, f, indent=2, ensure_ascii=False)
    print(f"JSON格式已保存: {output_json}")

    # 保存CSV格式
    with open(output_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['category', 'concept', 'frequency', 'disease_count', 'diseases'])

        # 修饰词
        for concept, info in sorted(concept_pool['modifiers'].items(),
                                    key=lambda x: -x[1]['frequency']):
            diseases_str = '; '.join(info['diseases'])
            writer.writerow([
                'modifier', concept, info['frequency'],
                info['disease_count'], diseases_str
            ])

        # 解剖概念
        for concept, info in sorted(concept_pool['anatomical_concepts'].items(),
                                    key=lambda x: -x[1]['frequency']):
            diseases_str = '; '.join(info['diseases'])
            writer.writerow([
                'anatomical', concept, info['frequency'],
                info['disease_count'], diseases_str
            ])

        # 特殊概念
        for concept, info in sorted(concept_pool['special_concepts'].items(),
                                    key=lambda x: -x[1]['frequency']):
            diseases_str = '; '.join(info['diseases'])
            writer.writerow([
                'special', concept, info['frequency'],
                info['disease_count'], diseases_str
            ])

    print(f"CSV格式已保存: {output_csv}")


def analyze_phrase_examples(disease_phrases, decomposer, num_examples=20):
    """分析并展示短语拆解示例"""
    print("\n" + "=" * 80)
    print("短语拆解示例 (以 pleural effusion 为例)")
    print("=" * 80)

    pe_phrases = disease_phrases.get('pleural effusion', [])
    if not pe_phrases:
        print("未找到 pleural effusion 的短语")
        return

    # 取前N个高频短语
    top_phrases = sorted(pe_phrases, key=lambda x: -x[1])[:num_examples]

    print(f"\n{'原始短语':<40} | {'修饰词':<30} | {'解剖概念':<30} | {'频次':>6}")
    print("-" * 120)

    for phrase, count in top_phrases:
        result = decomposer.decompose(phrase)
        modifiers = ', '.join(result['modifiers']) if result['modifiers'] else '-'
        anatomical = result['anatomical'] or '-'
        special = ' [特殊]' if result['is_special'] else ''

        print(f"{phrase:<40} | {modifiers:<30} | {anatomical:<30} | {count:>6}{special}")


def print_statistics(concept_pool):
    """打印统计信息"""
    print("\n" + "=" * 80)
    print("概念池统计")
    print("=" * 80)

    print(f"\n修饰词数量: {len(concept_pool['modifiers'])}")
    print(f"解剖概念数量: {len(concept_pool['anatomical_concepts'])}")
    print(f"特殊概念数量: {len(concept_pool['special_concepts'])}")

    print("\n[修饰词 TOP 20]")
    print("-" * 60)
    for i, (mod, info) in enumerate(list(concept_pool['modifiers'].items())[:20], 1):
        print(f"{i:2d}. {mod:20s} (频次: {info['frequency']:5d}, 疾病数: {info['disease_count']:2d})")

    print("\n[解剖概念 TOP 30]")
    print("-" * 60)
    for i, (ana, info) in enumerate(list(concept_pool['anatomical_concepts'].items())[:30], 1):
        print(f"{i:2d}. {ana:30s} (频次: {info['frequency']:5d}, 疾病数: {info['disease_count']:2d})")

    print("\n[特殊概念 TOP 10]")
    print("-" * 60)
    for i, (sp, info) in enumerate(list(concept_pool['special_concepts'].items())[:10], 1):
        print(f"{i:2d}. {sp:30s} (频次: {info['frequency']:5d}, 疾病数: {info['disease_count']:2d})")

    print(f"\n[拆解统计]")
    print("-" * 60)
    stats = concept_pool.get('stats', {})
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    input_csv = "disease_phrase_counts.csv"
    output_json = "location_concept_pool_v2.json"
    output_csv = "location_concepts_v2.csv"

    if not Path(input_csv).exists():
        print(f"错误: 文件不存在 - {input_csv}")
        exit(1)

    # 加载数据
    print("加载疾病-短语数据...")
    disease_phrases = load_disease_phrases(input_csv)
    print(f"加载了 {len(disease_phrases)} 种疾病")

    # 先展示拆解示例
    decomposer = PhraseDecomposer()
    analyze_phrase_examples(disease_phrases, decomposer)

    # 构建全局概念池
    print("\n构建全局概念池...")
    concept_pool = build_global_concept_pool(disease_phrases)

    # 保存结果
    save_concept_pool(concept_pool, output_json, output_csv)

    # 打印统计
    print_statistics(concept_pool)

    print("\n完成!")
