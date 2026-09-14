from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse
from app.config import settings
from app.services.auth import sync_user

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
    redirect_uri = request.url_for("auth_callback")
    return await oauth.corp_idp.authorize_redirect(request, redirect_uri)


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
    return RedirectResponse(url="/auth/login", status_code=302)
