from typing import Literal
from pydantic import BaseModel, Field


class EditSubmit(BaseModel):
    definition: str = Field(min_length=1)
    formula: str | None = None
    expected_version: int
    properties: dict[str, str] = Field(default_factory=dict)


class QueueItem(BaseModel):
    kind: Literal["new_term", "edit"]
    term_name: str
    definition: str
    formula: str | None
    properties: dict[str, str] = Field(default_factory=dict)


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1)
