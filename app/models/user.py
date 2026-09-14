from enum import Enum
from pydantic import BaseModel


class Role(str, Enum):
    EDITOR = "editor"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class UserOut(BaseModel):
    email: str
    role: Role
