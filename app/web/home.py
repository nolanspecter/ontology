from fastapi import APIRouter, Request, Depends
from app.web.templates import templates
from app.web.deps import get_web_user
from app.models.user import UserOut

router = APIRouter(tags=["web-home"])


@router.get("/")
def home_page(request: Request, user: UserOut | None = Depends(get_web_user)):
    return templates.TemplateResponse(request, "pages/home.html", {"current_user": user})
