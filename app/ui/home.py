from fastapi import APIRouter, Request, Depends
from app.ui.templates import templates
from app.ui.deps import get_web_user
from app.backend.models.user import UserOut

router = APIRouter(tags=["web-home"])


@router.get("/")
def home_page(request: Request, user: UserOut | None = Depends(get_web_user)):
    return templates.TemplateResponse(request, "pages/home.html", {"current_user": user})
