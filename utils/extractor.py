import pandas as pd
import re
import nltk
import spacy
from zai import ZhipuAiClient
from nltk.tokenize import sent_tokenize

# ====================== 【你需要修改的配置项】 ======================
# 1. 替换为你的GPT-4 API密钥（必填）
OPENAI_API_KEY = "d6393957e7fc44c3a14fd9aed7887fb1.80h3bBglXuvtXziT"
# 2. 替换为你的CSV文件路径（比如："C:/你的文件夹/你的CSV文件名.csv"）
INPUT_CSV_PATH = "/home/y530/handsome/DACG/data/preprocessed/mimic_cxr_preprocessed.csv"
# 3. 提取结果要保存的CSV路径（比如："C:/你的文件夹/提取结果.csv"）
OUTPUT_CSV_PATH = "/home/y530/handsome/DACG/data/mimic-cxr-a/extract_result.csv"
# 4. 中间结果保存路径（每100次GLM调用后保存）
INTERMEDIATE_OUTPUT_PATH = "/home/y530/handsome/DACG/data/mimic-cxr-a/extract_result_intermediate.csv"
# 5. 监督日志路径
SUPERVISION_LOG_PATH = "/home/y530/handsome/DACG/data/mimic-cxr-a/supervision_log.txt"
# 6. GLM调用保存间隔
SAVE_INTERVAL = 100
# ===============================================================

# 1. 初始化依赖（不用改）
try:
    nlp = spacy.load("en_ner_bc5cdr_md")  # 生物医学NER模型（提取疾病/位置）
except OSError:
    print("错误：未找到 en_ner_bc5cdr_md 模型，请运行：python -m spacy download en_ner_bc5cdr_md")
    exit(1)

nltk.download("punkt", quiet=True)    # 句子分词器
client = ZhipuAiClient(api_key=OPENAI_API_KEY)

# 全局变量用于跟踪GLM调用
glm_call_count = 0
processed_data = []  # 存储已处理的数据
# 2. 核心关键词表（不用改，对齐MIMIC-STRUC文档）
DISEASE_LIST = [
    "atelectasis", "cardiomegaly", "pleural effusion", "lung opacity", 
    "pneumonia", "edema", "pneumothorax", "consolidation", 
    "mass", "nodule", "emphysema", "fibrosis", 
    "pleural thickening", "calcinosis", "airway obstruction", 
    "bronchiectasis", "bronchitis", "pulmonary hypertension", 
    "asbestosis", "silicosis", "tuberculosis", "sarcoidosis", 
    "histoplasmosis", "coccidioidomycosis", "aspergillosis", 
    "lung cancer", "metastatic disease", "pleural mass", 
    "mediastinal mass", "hiatal hernia"
]
PROB_KEYWORDS = {
    3: ["there is", "demonstrates", "present"],  # 高置信度
    2: ["suggests", "likely", "possible"],       # 中置信度
    1: ["may be", "could be", "suspected"]       # 低置信度
}
SEVERITY_KEYWORDS = ["mild", "moderate", "severe", "minor"]  # 严重度
NEGATION_WORDS = ["no", "without", "absent", "no evidence of"]  # 否定词（区分阴性疾病）

# 3. 提取「阳性/阴性疾病」的函数（不用改）
def extract_diseases(full_report):
    # 把报告转小写，用spaCy识别疾病实体
    doc = nlp(full_report.lower())
    identified_diseases = [ent.text for ent in doc.ents if ent.label_ == "DISEASE"]
    
    positive_diseases = []  # 存在的疾病
    negative_diseases = []  # 不存在的疾病
    
    for disease in identified_diseases:
        # 匹配我们定义的30类疾病（只保留目标疾病）
        matched_disease = next((d for d in DISEASE_LIST if d in disease), None)
        if not matched_disease:
            continue
        
        # 找到疾病所在的句子，判断是否被否定（比如“no pneumothorax”）
        sentences = sent_tokenize(full_report.lower())
        target_sentence = next((s for s in sentences if disease in s), "")
        is_negative = any(neg_word in target_sentence for neg_word in NEGATION_WORDS)
        
        # 分类到阳性/阴性
        if is_negative:
            negative_diseases.append(matched_disease)
        else:
            positive_diseases.append(matched_disease)
    
    # 去重（避免同一疾病重复出现）
    return list(set(positive_diseases)), list(set(negative_diseases))

# 4. 提取「诊断置信度」的函数（不用改）
def extract_probability(full_report, target_disease):
    # 找到疾病所在的句子
    sentences = sent_tokenize(full_report.lower())
    target_sentence = next((s for s in sentences if target_disease in s), "")
    if not target_sentence:
        return 2  # 没找到句子，默认中置信度
    
    # 匹配置信度关键词，返回1-3分
    for score, keywords in PROB_KEYWORDS.items():
        if any(keyword in target_sentence for keyword in keywords):
            return score
    return 2  # 没匹配到关键词，默认中置信度

# 5. 提取「严重程度」的函数（不用改）
def extract_severity(full_report, target_disease):
    # 找到疾病所在的句子
    sentences = sent_tokenize(full_report.lower())
    target_sentence = next((s for s in sentences if target_disease in s), "")
    if not target_sentence:
        return None  # 没找到句子，返回空
    
    # 匹配严重度关键词（mild/moderate等）
    for severity in SEVERITY_KEYWORDS:
        if severity in target_sentence:
            return severity.capitalize()  # 首字母大写（比如Mild）
    return None  # 没匹配到，返回空

# 6. 提取「病灶位置」并标准化的函数（修复版本）
def extract_location(full_report, target_disease):
    # 第一步：找到疾病所在的句子，提取原始位置
    sentences = sent_tokenize(full_report.lower())
    target_sentence = next((s for s in sentences if target_disease in s), "")
    if not target_sentence:
        return None
    
    # 用spaCy识别句子中的解剖位置实体
    try:
        # 注意：en_ner_bc5cdr_md模型主要识别DISEASE实体，ANATOMICAL可能不存在
        # 我们使用更广泛的实体识别
        doc = nlp(target_sentence)
        
        # 尝试多种标签类型
        location_entities = []
        for ent in doc.ents:
            if ent.label_ in ["ANATOMICAL", "BODY_PART", "ORGAN", "LOCATION"]:
                location_entities.append(ent.text)
        
        # 如果没有找到解剖位置实体，使用规则匹配
        if not location_entities:
            # 基于规则的解剖位置匹配
            location_patterns = [
                r'\b(left|right|bilateral)\s+(lung|chest|pleura|hemithorax)\b',
                r'\b(upper|middle|lower)\s+(lobe|zone)\b',
                r'\b(right|left)\s+(upper|middle|lower)\s+(lobe|zone)\b',
                r'\b(basal|apical|hilar|mediastinal)\b',
                r'\b(lung\s+(fields|zones)|chest\s+(wall|cavity))\b'
            ]
            
            for pattern in location_patterns:
                match = re.search(pattern, target_sentence)
                if match:
                    location_entities.append(match.group(0))
                    break
        
        raw_location = location_entities[0] if location_entities else None
        if not raw_location:
            return None
        
    except Exception as e:
        print(f"位置实体识别出错（疾病：{target_disease}）：{e}")
        return None
    
    # 第二步：用GPT-4标准化位置（关闭流式输出）
    prompt = f"""Please refine the anatomical location to a medically accurate phrase:
Disease: {target_disease}
Raw Location: {raw_location}
Output only the refined location (no extra words)."""
    
    try:
        response = client.chat.completions.create(
            model="glm-4.5-flash",
            messages=[{"role": "user", "content": prompt}],
            thinking={
                    "type": "enabled",    # 启用深度思考模式
            },
            stream=False,              # 关闭流式输出（关键修复）
            max_tokens=4096,          # 最大输出 tokens
            temperature=0.1           # 控制输出的随机性
        )
        
        # 非流式模式下，可以直接访问完整响应
        refined_location = response.choices[0].message.content.strip()
        
        # 增加GLM调用计数（无论结果是否有效）
        global glm_call_count
        glm_call_count += 1
        
        # 基本验证：确保返回的不是空字符串
        if not refined_location or refined_location.lower() in ['none', 'null', 'n/a']:
            return raw_location  # 如果API返回无效结果，使用原始位置
        
        return refined_location
        
    except Exception as e:
        print(f"GLM调用出错（疾病：{target_disease}）：{e}")
        return raw_location  # 出错时返回原始位置而不是None

# 添加保存中间结果的函数
def save_intermediate_results():
    """保存中间处理结果到文件"""
    global processed_data
    
    if not processed_data:
        return
    
    try:
        # 创建临时DataFrame
        temp_df = pd.DataFrame(processed_data)
        
        # 保存到中间结果文件
        temp_df.to_csv(INTERMEDIATE_OUTPUT_PATH, index=False)
        
        # 记录到监督日志
        with open(SUPERVISION_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(f"\n=== 中间结果保存时间: {pd.Timestamp.now()} ===\n")
            f.write(f"已保存 {len(processed_data)} 条记录\n")
            f.write(f"GLM调用次数: {glm_call_count}\n")
            
            # 随机抽样显示结果质量（最多5条）
            if len(processed_data) > 0:
                sample_size = min(5, len(processed_data))
                sample_data = processed_data[-sample_size:]  # 取最后几条
                
                f.write(f"\n最近 {sample_size} 条记录样本:\n")
                for i, record in enumerate(sample_data, 1):
                    f.write(f"\n记录 {i}:\n")
                    f.write(f"  原始报告: {record.get('full_report', '')[:100]}...\n")
                    f.write(f"  阳性疾病: {record.get('positive_diseases_detail', [])}\n")
                    f.write(f"  阴性疾病: {record.get('negative_diseases', [])}\n")
        
        print(f"✅ 中间结果已保存到: {INTERMEDIATE_OUTPUT_PATH}")
        print(f"📝 监督日志已更新: {SUPERVISION_LOG_PATH}")
        
    except Exception as e:
        print(f"❌ 保存中间结果失败: {e}")

def log_supervision_info():
    """记录监督信息"""
    try:
        with open(SUPERVISION_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(f"\n--- GLM调用监控 ---\n")
            f.write(f"当前GLM调用次数: {glm_call_count}\n")
            f.write(f"下次保存阈值: {((glm_call_count // SAVE_INTERVAL) + 1) * SAVE_INTERVAL}\n")
            
            # 计算GLM调用统计
            if glm_call_count > 0:
                avg_calls_per_record = glm_call_count / len(processed_data) if processed_data else 0
                f.write(f"平均每条记录GLM调用次数: {avg_calls_per_record:.2f}\n")
    except Exception as e:
        print(f"记录监督信息失败: {e}")

# 7. 批量处理所有数据的主函数（增强版本）
def batch_extract():
    # 检查输入文件是否存在
    import os
    if not os.path.exists(INPUT_CSV_PATH):
        raise FileNotFoundError(f"输入文件不存在：{INPUT_CSV_PATH}")
    
    # 确保输出目录存在
    output_dir = os.path.dirname(OUTPUT_CSV_PATH)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"创建输出目录：{output_dir}")
    
    # 读取CSV文件
    df = pd.read_csv(INPUT_CSV_PATH)
    
    # 检查CSV是否有full_report列（必须有！）
    if "full_report" not in df.columns:
        raise ValueError("你的CSV缺少'full_report'列！请确认列名是否正确")
    
    print(f"开始处理 {len(df)} 行数据...")
    
    # 逐行提取信息
    def process_single_row(row):
        global processed_data, glm_call_count
        
        report = row["full_report"]
        
        # 处理空值
        if pd.isna(report) or not report.strip():
            result = pd.Series([[], []])
            # 记录空数据
            processed_data.append({
                'full_report': str(report),
                'positive_diseases_detail': [],
                'negative_diseases': []
            })
            return result
        
        # 提取阳性/阴性疾病
        pos_diseases, neg_diseases = extract_diseases(report)
        
        # 为每个阳性疾病提取置信度、严重度、位置
        pos_diseases_detail = []
        for disease in pos_diseases:
            prob = extract_probability(report, disease)
            sev = extract_severity(report, disease)
            loc = extract_location(report, disease)
            pos_diseases_detail.append({
                "disease": disease,
                "probability": prob,
                "severity": sev,
                "location": loc
            })
        
        result = pd.Series([pos_diseases_detail, neg_diseases])
        
        # 保存到全局处理数据列表
        processed_data.append({
            'full_report': str(report),
            'positive_diseases_detail': pos_diseases_detail,
            'negative_diseases': neg_diseases
        })
        
        # 检查是否需要保存中间结果
        if glm_call_count % SAVE_INTERVAL == 0 and glm_call_count > 0:
            print(f"\n🔍 GLM调用达到 {glm_call_count} 次，保存中间结果以便监督...")
            save_intermediate_results()
            log_supervision_info()
        
        return result
    
    # 执行提取
    print("开始提取信息...（耗时取决于数据量，GLM调用会稍慢）")
    start_time = None
    try:
        import time
        start_time = time.time()
    except:
        pass
    
    # 使用进度显示（如果数据量较大）
    if len(df) > 100:
        print("数据量较大，将显示进度...")
        processed = 0
        results = []
        
        for idx, row in df.iterrows():
            result = process_single_row(row)
            results.append(result)
            processed += 1
            
            # 显示处理进度
            if processed % 50 == 0:
                print(f"已处理 {processed}/{len(df)} 行 ({processed/len(df)*100:.1f}%)")
                # 显示GLM调用进度
                print(f"🔄 GLM调用统计: {glm_call_count} 次 (平均每行 {glm_call_count/processed:.2f} 次)")
        
        df[["positive_diseases_detail", "negative_diseases"]] = results
    else:
        df[["positive_diseases_detail", "negative_diseases"]] = df.apply(process_single_row, axis=1)
        
        # 对于小数据集，也显示GLM调用统计
        print(f"🔄 小数据集处理完成，GLM调用总数: {glm_call_count}")
    
    # 保存提取结果
    df.to_csv(OUTPUT_CSV_PATH, index=False)
    
    # 保存最终中间结果
    if processed_data:
        save_intermediate_results()
        
        # 最终监督日志
        with open(SUPERVISION_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(f"\n=== 最终处理完成 ===\n")
            f.write(f"总处理行数: {len(df)}\n")
            f.write(f"总GLM调用次数: {glm_call_count}\n")
            f.write(f"平均每行GLM调用次数: {glm_call_count/len(df):.2f}\n")
            f.write(f"最终保存时间: {pd.Timestamp.now()}\n")
    
    # 显示处理统计
    total_diseases = sum(len(diseases) for diseases in df["positive_diseases_detail"])
    print(f"✅ 提取完成！结果已保存到：{OUTPUT_CSV_PATH}")
    print(f"📊 处理统计：")
    print(f"   - 总行数：{len(df)}")
    print(f"   - GLM调用总次数：{glm_call_count}")
    print(f"   - 平均每行GLM调用次数：{glm_call_count/len(df):.2f}")
    print(f"   - 提取到的阳性疾病总数：{total_diseases}")
    print(f"   - 平均每行阳性疾病数：{total_diseases/len(df):.2f}")
    
    if start_time:
        end_time = time.time()
        print(f"   - 总耗时：{end_time - start_time:.2f}秒")
        
    # 提示监督文件位置
    print(f"\n👀 监督文件位置：")
    print(f"   - 中间结果：{INTERMEDIATE_OUTPUT_PATH}")
    print(f"   - 监督日志：{SUPERVISION_LOG_PATH}")
    print(f"   - 最终结果：{OUTPUT_CSV_PATH}")
    
    return df

# 运行脚本
if __name__ == "__main__":
    try:
        # 初始化监督日志
        with open(SUPERVISION_LOG_PATH, 'w', encoding='utf-8') as f:
            f.write(f"=== MIMIC-CXR 提取过程监督日志 ===\n")
            f.write(f"开始时间: {pd.Timestamp.now()}\n")
            f.write(f"输入文件: {INPUT_CSV_PATH}\n")
            f.write(f"输出文件: {OUTPUT_CSV_PATH}\n")
            f.write(f"中间结果文件: {INTERMEDIATE_OUTPUT_PATH}\n")
            f.write(f"GLM保存间隔: {SAVE_INTERVAL} 次调用\n")
            f.write(f"API模型: glm-4.5-flash\n")
            f.write(f"=" * 50 + "\n")
        
        print(f"📝 监督日志已初始化: {SUPERVISION_LOG_PATH}")
        print(f"🎯 GLM调用将每 {SAVE_INTERVAL} 次保存一次中间结果")
        
        # 执行批量提取
        batch_extract()
        
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断了处理过程")
        # 保存中断前的结果
        if processed_data:
            print("💾 保存中断前的处理结果...")
            save_intermediate_results()
        print("👋 处理已中断，可从监督日志查看进度")
        
    except Exception as e:
        print(f"❌ 处理出错：{e}")
        # 保存出错前的结果
        if processed_data:
            print("💾 保存出错前的处理结果...")
            save_intermediate_results()
        import traceback
        traceback.print_exc()