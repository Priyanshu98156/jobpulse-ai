"""Authentication API and OAuth Routes.

Handles user signup, bcrypt login, JWT session management via HTTP-only cookies,
and Google OAuth2 SSO authentication.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Form
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    set_auth_cookie,
    clear_auth_cookie,
    get_current_user_optional,
)
from app.db.session import get_db
from app.db.models import User, CandidateProfile
from app.services.gmail_service import gmail_reader_service

logger = logging.getLogger(__name__)

router = APIRouter()


class SignUpPayload(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = ""


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


@router.post("/signup")
async def api_signup(
    payload: SignUpPayload,
    response: Response,
    db: Session = Depends(get_db)
):
    """Provisions a new User, sets session cookie, and initializes workspace."""
    clean_email = payload.email.lower().strip()
    if len(payload.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long."
        )

    existing_user = db.query(User).filter(User.email == clean_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists."
        )

    hashed_pw = get_password_hash(payload.password)
    user = User(
        email=clean_email,
        hashed_password=hashed_pw,
        full_name=payload.full_name or clean_email.split("@")[0],
        auth_provider="local",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Automatically provision initial CandidateProfile linked to this user
    profile = db.query(CandidateProfile).filter(CandidateProfile.user_id == user.id).first()
    if not profile:
        profile = CandidateProfile(
            user_id=user.id,
            full_name=user.full_name,
            email=user.email
        )
        db.add(profile)
        db.commit()

    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    set_auth_cookie(response, token)

    return {
        "status": "success",
        "message": "Account created successfully.",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url
        },
        "redirect": "/dashboard"
    }


@router.post("/login")
async def api_login(
    payload: LoginPayload,
    response: Response,
    db: Session = Depends(get_db)
):
    """Authenticates user with email and bcrypt password, setting JWT cookie."""
    clean_email = payload.email.lower().strip()
    user = db.query(User).filter(User.email == clean_email).first()

    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated."
        )

    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    set_auth_cookie(response, token)

    return {
        "status": "success",
        "message": "Authenticated successfully.",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url
        },
        "redirect": "/dashboard"
    }


@router.post("/logout")
async def api_logout(response: Response):
    """Clears the session cookie."""
    clear_auth_cookie(response)
    return {"status": "success", "message": "Logged out successfully."}


@router.get("/me")
async def api_me(
    user: Optional[User] = Depends(get_current_user_optional)
):
    """Returns the currently authenticated user's profile or unauthenticated flag."""
    if not user:
        return {"authenticated": False, "user": None}
    return {
        "authenticated": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url,
            "auth_provider": user.auth_provider
        }
    }


@router.get("/google")
async def google_auth_initiate(request: Request):
    """Redirects user to Google OAuth2 consent screen for Sign-In."""
    config = gmail_reader_service.get_client_config()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth client secret is not configured in OS Keyring."
        )

    try:
        from google_auth_oauthlib.flow import Flow
        # Construct callback URL matching the incoming host header (e.g. localhost or 127.0.0.1)
        base_url = str(request.base_url).rstrip("/")
        callback_url = f"{base_url}/api/auth/google/callback"

        flow = Flow.from_client_config(
            config,
            scopes=[
                "openid",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile"
            ],
            redirect_uri=callback_url
        )
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="select_account"
        )
        response = RedirectResponse(url=auth_url)
        # Store PKCE code_verifier and state in temporary HttpOnly cookies
        if flow.code_verifier:
            response.set_cookie(
                key="oauth_code_verifier",
                value=flow.code_verifier,
                httponly=True,
                max_age=600,
                samesite="lax",
                secure=False
            )
        if state:
            response.set_cookie(
                key="oauth_state",
                value=state,
                httponly=True,
                max_age=600,
                samesite="lax",
                secure=False
            )
        return response
    except Exception as e:
        logger.error(f"Error initiating Google OAuth flow: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate Google Sign-In: {e}")


@router.get("/google/callback")
async def google_auth_callback(
    request: Request,
    code: Optional[str] = None,
    error: Optional[str] = None,
    state: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Handles Google OAuth2 callback, provisions user, and issues JWT session cookie."""
    if error or not code:
        logger.warning(f"Google OAuth denied or failed: error={error}")
        return RedirectResponse(url="/?auth_error=google_denied")

    config = gmail_reader_service.get_client_config()
    if not config:
        return RedirectResponse(url="/?auth_error=missing_oauth_config")

    try:
        import requests as http_requests
        from google_auth_oauthlib.flow import Flow

        base_url = str(request.base_url).rstrip("/")
        callback_url = f"{base_url}/api/auth/google/callback"
        cookie_state = request.cookies.get("oauth_state") or state

        flow = Flow.from_client_config(
            config,
            scopes=[
                "openid",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile"
            ],
            redirect_uri=callback_url,
            state=cookie_state
        )

        # Restore PKCE code_verifier from initiation turn
        code_verifier = request.cookies.get("oauth_code_verifier")
        if code_verifier:
            flow.code_verifier = code_verifier

        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Fetch Google user profile
        userinfo_resp = http_requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=10.0
        )
        if userinfo_resp.status_code != 200:
            logger.error(f"Failed to fetch Google userinfo: {userinfo_resp.text}")
            return RedirectResponse(url="/?auth_error=userinfo_failed")

        userinfo = userinfo_resp.json()
        email = userinfo.get("email", "").lower().strip()
        full_name = userinfo.get("name", "")
        avatar_url = userinfo.get("picture", "")

        if not email:
            return RedirectResponse(url="/?auth_error=no_email_returned")

        # Find or create User
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email,
                full_name=full_name or email.split("@")[0],
                avatar_url=avatar_url,
                auth_provider="google",
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            # Link default CandidateProfile
            profile = CandidateProfile(
                user_id=user.id,
                full_name=user.full_name,
                email=user.email
            )
            db.add(profile)
            db.commit()
        else:
            # Update avatar or name if newly provided
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
            if full_name and not user.full_name:
                user.full_name = full_name
            db.commit()

        token = create_access_token(data={"sub": str(user.id), "email": user.email})
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        set_auth_cookie(response, token)
        response.delete_cookie("oauth_code_verifier")
        response.delete_cookie("oauth_state")
        return response

    except Exception as e:
        logger.error(f"Error handling Google OAuth callback: {e}")
        err_resp = RedirectResponse(url=f"/?auth_error={str(e)}")
        err_resp.delete_cookie("oauth_code_verifier")
        err_resp.delete_cookie("oauth_state")
        return err_resp
