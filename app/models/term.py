from pydantic import BaseModel
from typing import Literal


class TermCreate(BaseModel):
    name: str
    definition: str
    formula: str | None = None


class TermOut(BaseModel):
    name: str
    definition: str
    formula: str | None
    status: Literal["draft", "pending_review", "published"]
    version: int
