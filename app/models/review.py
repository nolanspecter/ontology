from typing import Literal
from pydantic import BaseModel


class EditSubmit(BaseModel):
    definition: str
    formula: str | None = None
    expected_version: int


class QueueItem(BaseModel):
    kind: Literal["new_term", "edit"]
    term_name: str
    definition: str
    formula: str | None
