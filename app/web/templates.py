from pathlib import Path
from fastapi import Request
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"
