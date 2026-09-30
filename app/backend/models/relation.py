import re
from pydantic import BaseModel, Field, field_validator

RELATION_TYPE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,49}$")


def validate_relation_type(v: str) -> str:
    if not RELATION_TYPE_PATTERN.match(v):
        raise ValueError(
            "relation type must be uppercase letters, digits, and underscores, "
            "starting with a letter (max 50 characters)"
        )
    return v


class RelationCreate(BaseModel):
    target: str
    relation_type: str

    @field_validator("relation_type")
    @classmethod
    def _validate_relation_type(cls, v: str) -> str:
        return validate_relation_type(v)


class RelatedTermOut(BaseModel):
    """One outgoing typed relation from a term to another published term."""
    name: str = Field(description="The related term's exact name — pass this to get_term for its definition.")
    relation_type: str = Field(
        description="The relation's type, e.g. COMPUTED_FROM, PART_OF, OPPOSITE_OF, SYNONYM_OF, RELATED_TO, or a custom uppercase type."
    )
