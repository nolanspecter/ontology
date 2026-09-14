from enum import Enum
from pydantic import BaseModel


class RelationType(str, Enum):
    COMPUTED_FROM = "COMPUTED_FROM"
    PART_OF = "PART_OF"
    OPPOSITE_OF = "OPPOSITE_OF"
    SYNONYM_OF = "SYNONYM_OF"
    RELATED_TO = "RELATED_TO"


class RelationCreate(BaseModel):
    target: str
    relation_type: RelationType


class RelatedTermOut(BaseModel):
    name: str
    relation_type: RelationType
