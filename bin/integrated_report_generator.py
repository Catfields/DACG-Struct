#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成医疗图像报告生成系统
同时生成 Findings 和 Impressions 两个部分
"""

import torch
import torch.nn as nn
import argparse
import numpy as np
from PIL import Image
import torchvision.transforms as transforms
from modules.tokenizers import Tokenizer
from models.dacg import DACGModel
import json
import os
import time
import random
import re
from typing import Dict, Tuple, Optional, Any, List

try:
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover - 兼容旧 openai 库
    OpenAI = None
    try:
        import openai  # type: ignore
    except ImportError:
        openai = None  # type: ignore


def set_deterministic(seed: Optional[int] = 42):
    """为推理阶段设置确定性行为"""
    if seed is None:
        return

    os.environ["PYTHONHASHSEED"] = str(seed)
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    try:
        torch.use_deterministic_algorithms(True, warn_only=False)
    except Exception:
        torch.use_deterministic_algorithms(True, warn_only=True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False

    try:
        from torch.backends.cuda import sdp_kernel  # type: ignore
        sdp_kernel(enable_flash=False, enable_mem_efficient=False, enable_math=True)
    except Exception:
        pass


class OpenAITranslator:
    """封装 OpenAI GPT 翻译能力，缺失依赖或密钥时自动降级"""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.1,
        api_key: Optional[str] = None,
        enable: bool = True,
    ):
        self.model = model
        self.temperature = temperature
        self._available = False
        self._client: Optional[Any] = None
        self._legacy = None

        if not enable:
            print("ℹ️ 已关闭 GPT 翻译。")
            return

        # key = api_key or os.getenv("OPENAI_API_KEY")
        key="42e01064-4f61-46d6-abf6-e0a4a2c3808d"
        url="https://ark.cn-beijing.volces.com/api/v3"
        if not key:
            print("⚠️ 未检测到 OPENAI_API_KEY，翻译将跳过。")
            return

        try:
            if OpenAI is not None:
                self._client = OpenAI(api_key=key,base_url=url)
                self._available = True
            elif 'openai' in globals() and openai is not None:
                openai.api_key = key  # type: ignore
                self._legacy = openai  # type: ignore
                self._available = True
            else:
                print("⚠️ 未安装 openai SDK，翻译将跳过。")
        except Exception as exc:
            print(f"⚠️ 初始化 OpenAI 客户端失败: {exc}")
            self._available = False

    def translate(self, text: str) -> str:
        if not text or not self._available:
            return text

        def has_chinese(content: str) -> bool:
            return any("\u4e00" <= ch <= "\u9fff" for ch in content)

        def extract_chat_content(choice: Any) -> Optional[str]:
            message = getattr(choice, "message", None)
            if message is None and isinstance(choice, dict):
                message = choice.get("message")
            if message is None:
                return None
            content = getattr(message, "content", None)
            if content is None and isinstance(message, dict):
                content = message.get("content")
            return content

        base_prompt = (
            "请将以下英文医学影像报告内容翻译成专业、准确的中文医学描述，"
            "直接输出中文译文，不要包含英文或额外解释：\n"
            f"{text.strip()}"
        )
        strict_prompt = (
            "严格按照要求，仅输出中文译文，不要包含任何英文或附加说明：\n"
            f"{text.strip()}"
        )

        # 优先尝试新版 openai>=1.x 的 Chat Completions 接口
        try:
            if self._client is not None and hasattr(self._client, "chat"):
                resp = self._client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature,
                    messages=[
                        {"role": "system", "content": "You are a medical translation assistant."},
                        {"role": "user", "content": base_prompt},
                    ],
                )
                content = None
                if resp and getattr(resp, "choices", None):
                    content = extract_chat_content(resp.choices[0])
                if content and has_chinese(content):
                    return content.strip()
                if content:
                    print("ℹ️ Chat Completions 未返回中文译文，尝试严格重试。")
                    resp_strict = self._client.chat.completions.create(
                        model=self.model,
                        temperature=max(0.1, self.temperature),
                        messages=[
                            {"role": "system", "content": "You are a medical translation assistant. Only return the Chinese translation."},
                            {"role": "user", "content": strict_prompt},
                        ],
                    )
                    strict_content = None
                    if resp_strict and getattr(resp_strict, "choices", None):
                        strict_content = extract_chat_content(resp_strict.choices[0])
                    if strict_content and has_chinese(strict_content):
                        return strict_content.strip()
        except Exception as exc:
            print(f"⚠️ Chat Completions 翻译失败: {exc}")

        # 兼容 Responses API 不同的返回结构
        try:
            if self._client is not None and hasattr(self._client, "responses"):
                resp = self._client.responses.create(
                    model=self.model,
                    temperature=self.temperature,
                    input=base_prompt,
                )
                translated = getattr(resp, "output_text", None)
                if translated and has_chinese(translated):
                    return translated.strip()

                containers = getattr(resp, "output", None) or getattr(resp, "data", None) or []
                segments = []
                for item in containers:
                    content = getattr(item, "content", None) or getattr(item, "message", None) or getattr(item, "text", None)
                    if isinstance(content, list):
                        for entry in content:
                            if isinstance(entry, dict):
                                value = entry.get("text") or entry.get("value")
                                if value:
                                    segments.append(value)
                            else:
                                value = getattr(entry, "text", None) or getattr(entry, "value", None)
                                if value:
                                    segments.append(value)
                    elif isinstance(content, dict):
                        value = content.get("text") or content.get("value")
                        if value:
                            segments.append(value)
                    elif isinstance(content, str):
                        segments.append(content)
                if segments:
                    joined = "".join(segments).strip()
                    if has_chinese(joined):
                        return joined

                if self._client is not None and hasattr(self._client, "chat"):
                    print("ℹ️ Responses API 未返回中文译文，尝试严格重试。")
                    resp_strict = self._client.chat.completions.create(
                        model=self.model,
                        temperature=max(0.1, self.temperature),
                        messages=[
                            {"role": "system", "content": "You are a medical translation assistant. Only return the Chinese translation."},
                            {"role": "user", "content": strict_prompt},
                        ],
                    )
                    strict_content = None
                    if resp_strict and getattr(resp_strict, "choices", None):
                        strict_content = extract_chat_content(resp_strict.choices[0])
                    if strict_content and has_chinese(strict_content):
                        return strict_content.strip()
        except Exception as exc:
            print(f"⚠️ Responses API 翻译失败: {exc}")

        # 旧版 openai.ChatCompletion 接口
        try:
            if self._legacy is not None:
                resp = self._legacy.ChatCompletion.create(  # type: ignore
                    model=self.model,
                    temperature=self.temperature,
                    messages=[
                        {"role": "system", "content": "You are a medical translation assistant."},
                        {"role": "user", "content": base_prompt},
                    ],
                )
                choices = resp.get("choices", [])
                if choices:
                    message = choices[0].get("message", {})
                    content = message.get("content")
                    if content and has_chinese(content):
                        return content.strip()
        except Exception as exc:
            print(f"⚠️ 旧版 ChatCompletion 翻译失败: {exc}")

        print("⚠️ 翻译未能生成中文，将返回原文。")
        return text


class IntegratedMedicalReportGenerator:
    """集成医疗图像报告生成器"""

    def __init__(self,
                 findings_model_path: str = "results/mimic_cxr_a_findings",
                 impressions_model_path: str = "results/mimic_cxr_a_impressions",
                 device: str = "cuda" if torch.cuda.is_available() else "cpu",
                 decode_strategy: str = "beam",
                 beam_size: int = 10,
                 temperature: float = 1.0,
                 top_k: int = 50,
                 top_p: float = 0.9,
                 deterministic_seed: Optional[int] = 42,
                 translate_to_zh: bool = True,
                 translator_backend: str = "openai",
                 translator_model_findings: str = "ep-20251018154549-2z528",
                 translator_model_impressions: str = "ep-20251018154549-2z528",
                 translator_temperature: float = 0.1,
                 translator_api_key: Optional[str] = None,
                 translator_model: Optional[str] = None):
        """
        初始化集成模型

        Args:
            findings_model_path: findings模型路径
            impressions_model_path: impressions模型路径
            device: 计算设备
            decode_strategy: 解码策略，可选 beam、greedy、top-k、top-p、multinomial
            beam_size: beam-search 的宽度
            temperature: 采样温度
            top_k: top-k 采样的 k
            top_p: top-p 采样的累积概率阈值
            deterministic_seed: 确定性随机种子，设置为None可禁用
            translate_to_zh: 是否启用中文翻译
            translator_backend: 翻译后端（目前支持 openai）
            translator_model_findings: Findings 段使用的模型名（默认 gpt-4o）
            translator_model_impressions: Impressions 段使用的模型名（默认 gpt-5-nano）
            translator_temperature: 翻译采样温度
            translator_api_key: 可选的显式 API key
            translator_model: 兼容旧参数；如提供且未显式设置 per-section，将两段均使用此模型
        """
        set_deterministic(deterministic_seed)

        self.device = device
        self.repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.decode_strategy = decode_strategy
        self.beam_size = beam_size
        self.temperature = temperature
        self.top_k = top_k
        self.top_p = top_p
        self.translate_to_zh = translate_to_zh and translator_backend == "openai"

        findings_root = self._resolve_path(findings_model_path)
        impressions_root = self._resolve_path(impressions_model_path)

        # 加载findings模型
        self.findings_model, self.findings_tokenizer = self._load_model(
            findings_root, "findings"
        )

        # 加载impressions模型
        self.impressions_model, self.impressions_tokenizer = self._load_model(
            impressions_root, "impressions"
        )

        # 初始化两个独立的翻译器，默认使用不同模型以规避服务端缓存
        self.translator = None  # 保留以兼容旧逻辑
        self.findings_translator = None
        self.impressions_translator = None
        if self.translate_to_zh:
            if translator_backend != "openai":
                print(f"⚠️ 暂不支持的翻译后端: {translator_backend}，翻译被禁用。")
                self.translate_to_zh = False
            else:
                # 兼容旧参数 translator_model；若提供且未设置 per-section，则两段均用同一模型
                f_model = translator_model_findings or translator_model or "gpt-4o"
                i_model = translator_model_impressions or translator_model or "gpt-5-nano"

                self.findings_translator = OpenAITranslator(
                    model=f_model,
                    temperature=translator_temperature,
                    api_key=translator_api_key,
                    enable=True,
                )
                self.impressions_translator = OpenAITranslator(
                    model=i_model,
                    temperature=translator_temperature,
                    api_key=translator_api_key,
                    enable=True,
                )

                f_ok = getattr(self.findings_translator, "_available", False)
                i_ok = getattr(self.impressions_translator, "_available", False)
                if not f_ok and not i_ok:
                    self.translate_to_zh = False
                    print("⚠️ 翻译不可用，系统将直接返回英文内容。")
                else:
                    print(f"✅ 翻译功能已启用: Findings→{f_model}  Impressions→{i_model}")

        # 图像预处理
        self.image_transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                               std=[0.229, 0.224, 0.225])
        ])

        print("✅ 集成医疗图像报告生成器初始化完成")

    # =======================
    # Findings 结构化映射配置
    # =======================
    REPORT_TO_SEG = {
        "lungs_and_airways": ["right_lung", "left_lung"],
        "cardiac_mediastinal": ["heart"],
        "pleura": [],
        "diaphragm": [],
        "bones": [],
        "lines_tubes_devices": [],
    }

    ORGAN_REGEX: Dict[str, List[re.Pattern]] = {
        "lungs_and_airways": [
            re.compile(r"\blung[s]?\b", re.I),
            re.compile(r"\bpulmon", re.I),
            re.compile(r"\bbronch", re.I),
            re.compile(r"\bairway", re.I),
            re.compile(r"\bconsolidat", re.I),
            re.compile(r"\batelectas", re.I),
            re.compile(r"\binfiltrat", re.I),
            re.compile(r"\bpneumonia\b|\bpneumonitis\b", re.I),
            re.compile(r"\bedema|emphysema|fibros", re.I),
            re.compile(r"\bpneumothorax\b|\bptx\b", re.I),
            re.compile(r"\bnodule|mass(es)?\b", re.I),
        ],
        "cardiac_mediastinal": [
            re.compile(r"\bcardi(o|ac)\b", re.I),
            re.compile(r"\bheart\b", re.I),
            re.compile(r"\bcardiomegaly\b", re.I),
            re.compile(r"\bmediastin", re.I),
            re.compile(r"\baorta|aortic\b", re.I),
            re.compile(r"\bsilhouette\b", re.I),
        ],
        "pleura": [
            re.compile(r"\bpleur", re.I),
            re.compile(r"\beffusion\b", re.I),
            re.compile(r"\bcostophrenic\b", re.I),
        ],
        "diaphragm": [
            re.compile(r"\bdiaphragm", re.I),
            re.compile(r"\belevat(ed|ion)? hemidiaphragm", re.I),
        ],
        "bones": [
            re.compile(r"\brib(s)?\b", re.I),
            re.compile(r"\bclavicle\b|\bhumer(us|i)\b|\bscapula\b", re.I),
            re.compile(r"\bspine\b|\bvertebra", re.I),
            re.compile(r"\bfracture|lytic|sclerotic|degenerative", re.I),
        ],
        "lines_tubes_devices": [
            re.compile(r"\bendotracheal\b|\bet tube\b|\btrach", re.I),
            re.compile(r"\bcentral (venous )?catheter\b|\bcvc\b|\bpicc\b", re.I),
            re.compile(r"\bchest tube\b|\bthoracostomy\b", re.I),
            re.compile(r"\bpacemaker\b|lead(s)?\b", re.I),
        ],
    }

    ORGAN_PRIORITIES: List[str] = [
        "lines_tubes_devices",
        "pleura",
        "cardiac_mediastinal",
        "lungs_and_airways",
        "diaphragm",
        "bones",
    ]

    def _resolve_path(self, path: str) -> str:
        """保证路径相对于仓库根目录解析"""
        if os.path.isabs(path):
            return path
        return os.path.abspath(os.path.join(self.repo_root, path))

    def _load_model(self, model_path: str, model_type: str) -> Tuple[nn.Module, Tokenizer]:
        """加载单个模型和对应的tokenizer"""
        # 创建模拟的args
        args = argparse.Namespace()
        args.d_model = 512
        args.num_layers = 3
        args.num_heads = 8
        args.d_ff = 512
        args.dropout = 0.1
        args.max_seq_length = 100 if model_type == "findings" else 40
        args.visual_extractor = 'resnet101'
        args.visual_extractor_pretrained = True
        args.dataset_name = 'mimic_cxr'
        args.visual_feat_dim = 2048
        args.H = 3

        # 加载tokenizer
        tokenizer_path = os.path.join(model_path, "vocab.json")
        if os.path.exists(tokenizer_path):
            tokenizer = Tokenizer(args)
            tokenizer.load_vocab(tokenizer_path)
        else:
            print(f"⚠️  未找到词汇表文件: {tokenizer_path}，创建新的tokenizer")
            tokenizer = Tokenizer(args)

        # 创建模型
        model = DACGModel(args, tokenizer)

        # 加载模型权重
        model_path_file = os.path.join(model_path, "model_best", "model.safetensors")
        if os.path.exists(model_path_file):
            try:
                from safetensors.torch import load_file
                state_dict = load_file(model_path_file)
                model.load_state_dict(state_dict, strict=False)
                print(f"✅ 成功加载{model_type}模型权重")
            except Exception as e:
                print(f"⚠️  加载{model_type}模型权重失败: {e}")
                print("使用随机初始化权重")
        else:
            print(f"⚠️  未找到{model_type}模型文件: {model_path_file}")

        model.to(self.device)
        model.eval()

        return model, tokenizer

    @staticmethod
    def _contains_chinese(text: str) -> bool:
        """简单检测文本中是否包含中文字符"""
        return any("\u4e00" <= ch <= "\u9fff" for ch in text)

    def _preprocess_image(self, image_path: str) -> torch.Tensor:
        """预处理输入图像"""
        image = Image.open(image_path).convert('RGB')
        image_tensor = self.image_transform(image)
        return image_tensor.unsqueeze(0)  # 添加batch维度

    def _tokens_to_text(self, tokens: torch.Tensor, tokenizer: Tokenizer) -> str:
        """将token序列转换为文本"""
        tokens = tokens.cpu().numpy()
        text = []

        for token_id in tokens[0]:  # 取第一个样本
            if token_id == tokenizer.eos_id:
                break
            if token_id != tokenizer.pad_id and token_id != tokenizer.bos_id:
                # 获取对应的词汇
                for word, idx in tokenizer.token2idx.items():
                    if idx == token_id:
                        text.append(word)
                        break

        return ' '.join(text)

    def _translate_if_needed(self, english_text: str, *, prompt_prefix: Optional[str] = None, translator: Optional[Any] = None) -> str:
        """调用翻译后端，失败则返回原文；可注入特定翻译器以实现分段使用不同模型"""
        if not english_text or not self.translate_to_zh:
            return english_text

        trans = translator or getattr(self, "translator", None)
        if trans is None:
            return english_text

        text_to_translate = english_text
        if prompt_prefix:
            text_to_translate = f"{prompt_prefix.strip()}\n{english_text.strip()}"

        translated = trans.translate(text_to_translate).strip()
        if not self._contains_chinese(translated):
            print("⚠️ 翻译结果缺少中文内容，将回退为原文或英文描述。")
            return english_text
        return translated

    def generate_report(self, image_path: str) -> Dict[str, str]:
        """
        生成完整的医疗报告

        Args:
            image_path: 输入图像路径

        Returns:
            包含findings和impressions的字典
        """
        try:
            # 预处理图像
            image_tensor = self._preprocess_image(image_path)
            image_tensor = image_tensor.to(self.device)

            print(f"🔍 正在处理图像: {image_path}")

            # 生成findings
            with torch.no_grad():
                findings_seq = self.findings_model(
                    image_tensor,
                    mode='sample',
                    decode=self.decode_strategy,
                    beam_size=self.beam_size,
                    temperature=self.temperature,
                    top_k=self.top_k,
                    top_p=self.top_p
                )
                findings_text = self._tokens_to_text(findings_seq, self.findings_tokenizer)

            # 生成impressions
            with torch.no_grad():
                impressions_seq = self.impressions_model(
                    image_tensor,
                    mode='sample',
                    decode=self.decode_strategy,
                    beam_size=self.beam_size,
                    temperature=self.temperature,
                    top_k=self.top_k,
                    top_p=self.top_p
                )
                impressions_text = self._tokens_to_text(impressions_seq, self.impressions_tokenizer)

            findings_prompt_prefix = "以下内容为放射学检查所见 (Findings)，请翻译成专业、准确的中文医学表述.译文外，不输出任何其他内容"
            impressions_prompt_prefix = "请将以下放射学诊断印象（Impressions）内容，翻译成专业、准确的中文医学结论。译文外，不输出任何其他内容"

            findings_text_zh = self._translate_if_needed(findings_text, prompt_prefix=findings_prompt_prefix, translator=self.findings_translator)
            print(f"[DEBUG] Findings 翻译完成: {findings_text_zh[:50]}")
            impressions_text_zh = self._translate_if_needed(impressions_text, prompt_prefix=impressions_prompt_prefix, translator=self.impressions_translator)
            print(f"[DEBUG] Impressions 翻译完成: {impressions_text_zh[:50]}")
            # 验证是否相同
            if findings_text_zh == impressions_text_zh:
                print("⚠️ 警告：两次翻译结果相同！")
                print(f"Findings 原文: {findings_text[:100]}")
                print(f"Impressions 原文: {impressions_text[:100]}")
    

            report = {
                "findings": findings_text,
                "findings_zh": findings_text_zh,
                "impressions": impressions_text,
                "impressions_zh": impressions_text_zh,
                "structured_findings_by_organ": self.structure_findings_by_organ(
                    findings_text,
                    translate_to_zh=self.translate_to_zh,
                ),
                "image_path": image_path
            }

            print("✅ 报告生成完成")
            return report

        except Exception as e:
            print(f"❌ 生成报告时出错: {e}")
            return {
                "findings": f"生成失败: {str(e)}",
                "findings_zh": f"生成失败: {str(e)}",
                "impressions": f"生成失败: {str(e)}",
                "impressions_zh": f"生成失败: {str(e)}",
                "structured_findings_by_organ": {},
                "image_path": image_path
            }

    def generate_batch_reports(self, image_paths: list) -> list:
        """批量生成报告"""
        reports = []
        for image_path in image_paths:
            report = self.generate_report(image_path)
            reports.append(report)
        return reports

    def save_report(self, report: Dict[str, str], output_path: str):
        """保存报告到文件"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"✅ 报告已保存到: {output_path}")
        except Exception as e:
            print(f"❌ 保存报告失败: {e}")

    # =======================
    # Findings 结构化辅助方法
    # =======================

    def _split_sentences_en(self, text: str) -> List[str]:
        """将英文 findings 拆分为句子级片段"""
        if not text:
            return []
        parts = re.split(r"(?<=[\.\!\?])\s+", text.strip())
        return [p.strip() for p in parts if p.strip()]

    def _classify_sentence_to_organ(self, sentence: str) -> str:
        """根据关键词匹配将句子归类到器官"""
        if not sentence:
            return "other"
        scores: Dict[str, int] = {}
        for organ, patterns in self.ORGAN_REGEX.items():
            scores[organ] = sum(1 for pattern in patterns if pattern.search(sentence) is not None)
        max_score = max(scores.values(), default=0)
        if max_score == 0:
            return "other"
        winners = [organ for organ, score in scores.items() if score == max_score]
        for priority in self.ORGAN_PRIORITIES:
            if priority in winners:
                return priority
        return winners[0]

    def structure_findings_by_organ(self, findings_en: str, translate_to_zh: bool = True) -> Dict[str, Any]:
        """
        将英文 findings 字段按器官分桶，返回中英文对齐的结构化结果
        """
        sentences = self._split_sentences_en(findings_en)
        buckets: Dict[str, Dict[str, Any]] = {}
        base_organs = list(self.ORGAN_REGEX.keys()) + ["other"]
        for organ in base_organs:
            buckets[organ] = {
                "sentences_en": [],
                "sentences_zh": [],
                "text_en": "",
                "text_zh": "",
                "segmentation_keys": self.REPORT_TO_SEG.get(organ, []),
            }

        for sentence in sentences:
            organ = self._classify_sentence_to_organ(sentence)
            if organ not in buckets:
                buckets[organ] = {
                    "sentences_en": [],
                    "sentences_zh": [],
                    "text_en": "",
                    "text_zh": "",
                    "segmentation_keys": self.REPORT_TO_SEG.get(organ, []),
                }
            buckets[organ]["sentences_en"].append(sentence)

        if translate_to_zh and self.findings_translator is not None:
            for organ, data in buckets.items():
                zh_sentences: List[str] = []
                for sentence in data["sentences_en"]:
                    translated = self.findings_translator.translate(sentence)
                    zh_sentences.append(translated.strip() if translated else sentence)
                data["sentences_zh"] = zh_sentences
                data["text_en"] = " ".join(data["sentences_en"]).strip()
                data["text_zh"] = " ".join(data["sentences_zh"]).strip()
        else:
            for data in buckets.values():
                data["text_en"] = " ".join(data["sentences_en"]).strip()
                data["text_zh"] = ""

        # 可选：剔除完全为空的器官
        return {organ: info for organ, info in buckets.items() if info["sentences_en"]}


def main():
    """主函数"""
    # 初始化集成模型
    generator = IntegratedMedicalReportGenerator()

    # 单张图像测试
    image_path = "data/mimic-cxr-a/official_data_iccv_final/files/p1/p10000032/s55612275.jpg"

    if os.path.exists(image_path):
        # 生成报告
        report = generator.generate_report(image_path)

        # 打印结果
        print("\n" + "="*50)
        print("🏥 生成的医疗报告")
        print("="*50)
        print(f"图像路径: {report['image_path']}")
        print(f"\n📋 检查发现 (Findings):")
        print(report['findings'])
        print(f"\n💭 诊断印象 (Impressions):")
        print(report['impressions'])
        print("="*50)

        # 保存报告
        output_path = "generated_report.json"
        generator.save_report(report, output_path)
    else:
        print(f"❌ 图像文件不存在: {image_path}")
        print("请修改image_path为实际存在的图像路径")


if __name__ == "__main__":
    # main()
    text_1="the lungs are clear without focal consolidation . no pleural effusion or pneumothorax is seen . the cardiac and mediastinal silhouettes are unremarkable ."
    text_2="no acute cardiopulmonary process ."
    mock_translator1=OpenAITranslator(model="gpt-4o")
    mock_translator2=OpenAITranslator(model="gpt-5-nano")
    zh_text_1=mock_translator1.translate(text_1)
    zh_text_2=mock_translator2.translate(text_2)
    print(f"findings:{zh_text_1}")
    print(f"impressions:{zh_text_2}")
