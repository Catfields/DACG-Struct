from pydantic import BaseModel


class TranslationIn(BaseModel):
    english_text: str


class TranslationOut(BaseModel):
    english_text: str
    chinese_text: str
    status: int
