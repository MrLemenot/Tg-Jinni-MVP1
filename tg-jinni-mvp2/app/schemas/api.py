from pydantic import BaseModel, Field

class InitData(BaseModel):
    telegram_id: int
    username: str | None = None
    first_name: str | None = None

class AnswerRequest(BaseModel):
    question_id: int
    answer: float = Field(ge=0, le=1)

class ProposeEntity(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    username: str

class CreatePromotion(BaseModel):
    entity_id: int
