from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal
from app.models.term_kind import TERM_KINDS


class TermCreate(BaseModel):
    name: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    formula: str | None = None
    kind: str | None = None
    properties: dict[str, str] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def name_must_be_url_safe(cls, v: str) -> str:
        if any(c in v for c in "/#?"):
            raise ValueError("name cannot contain '/', '#', or '?'")
        return v

    @model_validator(mode="after")
    def _validate_kind_and_properties(self) -> "TermCreate":
        if self.kind is None:
            if self.properties:
                raise ValueError("properties require a kind")
            return self
        if self.kind not in TERM_KINDS:
            raise ValueError(f"unknown kind '{self.kind}'")
        missing = [
            p.name for p in TERM_KINDS[self.kind]
            if p.required and not self.properties.get(p.name)
        ]
        if missing:
            noun = "property" if len(missing) == 1 else "properties"
            raise ValueError(f"missing required {noun}: {', '.join(missing)}")
        return self


class TermOut(BaseModel):
    name: str
    definition: str
    formula: str | None
    status: Literal["draft", "pending_review", "published"]
    version: int
    created_by: str | None = None
    kind: str | None = None
    properties: dict[str, str] = Field(default_factory=dict)
