from pydantic import BaseModel, Field, field_validator
from typing import Literal


class TermCreate(BaseModel):
    name: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    formula: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_be_url_safe(cls, v: str) -> str:
        if any(c in v for c in "/#?"):
            raise ValueError("name cannot contain '/', '#', or '?'")
        return v


class TermOut(BaseModel):
    name: str
    definition: str
    formula: str | None
    status: Literal["draft", "pending_review", "published"]
    version: int
