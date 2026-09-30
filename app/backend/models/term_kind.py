from pydantic import BaseModel


class PropertyDef(BaseModel):
    name: str
    required: bool = False


TERM_KINDS: dict[str, list[PropertyDef]] = {
    "Person": [
        PropertyDef(name="title"),
        PropertyDef(name="department"),
    ],
    "Business": [
        PropertyDef(name="ticker"),
        PropertyDef(name="jurisdiction"),
    ],
}
