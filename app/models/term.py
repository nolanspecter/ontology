from pydantic import BaseModel, Field
from typing import Literal


class TermCreate(BaseModel):
    name: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    formula: str | None = None


class TermOut(BaseModel):
    name: str
    definition: str
    formula: str | None
    status: Literal["draft", "pending_review", "published"]
    version: int
