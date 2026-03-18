import asyncio
import logging
from openai import OpenAI
from app.config import settings

_client = OpenAI(api_key=settings.DOUBAO_API_KEY, base_url=settings.DOUBAO_BASE_URL)
_logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是一名专业医学翻译助手，专门将英文放射影像诊断描述翻译为规范的中文医学术语。
要求：
1. 严格使用中文医学标准术语，不使用口语化表达。
2. 保留所有数值、单位及标点符号的准确性。
3. 禁止添加任何原文未包含的诊断结论或主观推断。
4. 仅返回翻译结果，不附加解释或说明。"""


async def translate(english_text: str) -> tuple[str, int]:
    """
    将英文诊断条目翻译为规范中文医学术语。
    Returns: (chinese_text, status)  status: 1=成功, 0=失败（降级返回原文）
    """

    def _call() -> str:
        resp = _client.chat.completions.create(
            model="doubao-pro",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": english_text},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""

    try:
        text = await asyncio.to_thread(_call)
    except Exception as exc:  # pragma: no cover
        _logger.error("翻译失败: %s", exc)
        return english_text, 0

    if not text.strip():
        return english_text, 0

    return text, 1
