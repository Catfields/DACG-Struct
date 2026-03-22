import asyncio
import json
import logging
import re
import urllib.request
from app.config import settings
_logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是一名专业医学翻译助手，专门将英文放射影像诊断描述翻译为规范的中文医学术语。
要求：
1. 严格使用中文医学标准术语，不使用口语化表达。
2. 保留所有数值、单位及标点符号的准确性。
3. 禁止添加任何原文未包含的诊断结论或主观推断。
4. 仅返回翻译结果，不附加解释或说明。"""


def _mock_translate(text: str) -> str:
    # Lightweight, deterministic demo translator (NOT for clinical use).
    replacements = [
        (r"\bno acute cardiopulmonary abnormality\b", "未见急性心肺异常"),
        (r"\bheart size is normal\b", "心影大小正常"),
        (r"\bheart size normal\b", "心影大小正常"),
        (r"\blungs are clear\b", "双肺清晰"),
        (r"\bno focal consolidation\b", "未见局灶性实变"),
        (r"\bno pleural effusion\b", "未见胸腔积液"),
        (r"\bpleural effusion\b", "胸腔积液"),
        (r"\bpneumothorax\b", "气胸"),
        (r"\bcardiomegaly\b", "心脏增大"),
        (r"\bconsolidation\b", "实变"),
        (r"\bopacity\b", "致密影"),
        (r"\binfiltrate\b", "浸润影"),
        (r"\bedema\b", "水肿"),
        (r"\bfracture\b", "骨折"),
        (r"\bno\b", "未见"),
        (r"\bnormal\b", "正常"),
        (r"\bheart\b", "心脏"),
        (r"\blung(s)?\b", "肺"),
        (r"\bpleura\b", "胸膜"),
    ]

    out = text
    for pattern, replacement in replacements:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return out


async def translate(english_text: str) -> tuple[str, int]:
    """
    将英文诊断条目翻译为规范中文医学术语。
    Returns: (chinese_text, status)  status: 1=成功, 0=失败（降级返回原文）
    """

    mode = settings.TRANSLATION_MODE.lower().strip()
    if mode == "mock":
        return _mock_translate(english_text), 1

    def _extract_text(data: dict) -> str:
        if not isinstance(data, dict):
            return ""
        if isinstance(data.get("output_text"), str) and data["output_text"].strip():
            return data["output_text"]
        output = data.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for c in content:
                        if not isinstance(c, dict):
                            continue
                        if c.get("type") in ("output_text", "text") and isinstance(c.get("text"), str):
                            if c["text"].strip():
                                return c["text"]
                if isinstance(item.get("text"), str) and item["text"].strip():
                    return item["text"]
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message", {})
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                return msg["content"]
        return ""

    def _call() -> str:
        url = settings.DOUBAO_BASE_URL.rstrip("/") + "/responses"
        payload = {
            "model": settings.DOUBAO_MODEL,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": english_text,
                            "translation_options": {
                                "source_language": "en",
                                "target_language": "zh",
                            },
                        }
                    ],
                }
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {settings.DOUBAO_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
        return _extract_text(json.loads(body))

    try:
        text = await asyncio.to_thread(_call)
    except Exception as exc:  # pragma: no cover
        _logger.error("翻译失败: %s", exc)
        return english_text, 0

    if not text.strip():
        return english_text, 0

    return text, 1
