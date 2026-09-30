from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request, Form
from starlette.responses import RedirectResponse
from app.backend.config import settings
from app.backend.services.auth import sync_user, get_user
from app.ui.templates import templates

oauth = OAuth()
oauth.register(
    name="corp_idp",
    client_id=settings.oidc_client_id,
    client_secret=settings.oidc_client_secret,
    server_metadata_url=settings.oidc_server_metadata_url,
    client_kwargs={"scope": "openid email profile groups"},
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    if settings.env == "dev":
        return templates.TemplateResponse(request, "pages/dev_login.html", {"current_user": None, "error": None})
    redirect_uri = request.url_for("auth_callback")
    return await oauth.corp_idp.authorize_redirect(request, redirect_uri)


if settings.env == "dev":

    @router.post("/dev-login")
    async def dev_login(request: Request, email: str = Form(""), password: str = Form("")):
        user = get_user(email) if email else None
        if user is None or password != settings.dev_login_password:
            return templates.TemplateResponse(
                request,
                "pages/dev_login.html",
                {"current_user": None, "error": "Invalid email or password."},
                status_code=401,
            )
        request.session["user_email"] = user.email
        return RedirectResponse(url="/", status_code=302)


@router.get("/callback", name="auth_callback")
async def auth_callback(request: Request):
    token = await oauth.corp_idp.authorize_access_token(request)
    claims = token["userinfo"]
    user = sync_user(email=claims["email"], groups=claims.get("groups", []))
    request.session["user_email"] = user.email
    return RedirectResponse(url="/")


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)
