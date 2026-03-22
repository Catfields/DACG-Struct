from fastapi import APIRouter
from app.schemas.translation import TranslationIn, TranslationOut
from app.services import translation_service
from app.core.exceptions import AppException

router = APIRouter(prefix="/translate", tags=["translate"])


@router.post("", response_model=TranslationOut)
async def translate_text(payload: TranslationIn):
    text = payload.english_text.strip()
    if not text:
        raise AppException("EMPTY_TEXT", "英文文本不能为空", status_code=400)

    chinese_text, status = await translation_service.translate(text)
    return TranslationOut(english_text=text, chinese_text=chinese_text, status=status)
