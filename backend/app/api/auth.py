import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.security import create_access_token
from ..deps import get_current_user, get_db
from ..models.user import User
from ..schemas.auth import LoginRequest, TokenResponse, UserMe
from ..services.auth import authenticate

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate(db, payload.username, payload.password)
    if not user:
        log.warning("Failed login attempt for user '%s'", payload.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    settings = get_settings()
    token = create_access_token(subject=user.username, extra={"is_admin": user.is_admin})
    return TokenResponse(access_token=token, expires_in=settings.JWT_EXPIRE_MINUTES * 60)


@router.get("/me", response_model=UserMe)
def me(current: User = Depends(get_current_user)) -> UserMe:
    return UserMe(username=current.username, is_admin=current.is_admin)
