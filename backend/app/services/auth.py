import logging

from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.security import hash_password, verify_password
from ..models.user import User

log = logging.getLogger(__name__)


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username, User.is_active.is_(True)).one_or_none()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def ensure_admin_user(db: Session) -> None:
    settings = get_settings()
    existing = db.query(User).filter(User.username == settings.ADMIN_USERNAME).one_or_none()
    if existing:
        return
    admin = User(
        username=settings.ADMIN_USERNAME,
        password_hash=hash_password(settings.ADMIN_PASSWORD),
        is_admin=True,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    log.info("Seeded admin user '%s'", settings.ADMIN_USERNAME)
