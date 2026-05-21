import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode

import httpx
import msal
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.microsoft_account import MicrosoftAccount
from ..models.user import User

log = logging.getLogger(__name__)


GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES: tuple[str, ...] = (
    "User.Read",
    "Calendars.Read",
    "OnlineMeetings.Read",
    "OnlineMeetings.ReadWrite",
    "OnlineMeetingRecording.Read.All",
    "OnlineMeetingTranscript.Read.All",
)


class MsGraphError(RuntimeError):
    pass


class MsNotConnectedError(MsGraphError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _msal_app() -> msal.ConfidentialClientApplication:
    s = get_settings()
    if not s.MS_CLIENT_ID or not s.MS_CLIENT_SECRET:
        raise MsGraphError("Microsoft Graph integration is not configured (MS_CLIENT_ID/MS_CLIENT_SECRET missing)")
    authority = f"https://login.microsoftonline.com/{s.MS_TENANT_ID or 'common'}"
    return msal.ConfidentialClientApplication(
        client_id=s.MS_CLIENT_ID,
        client_credential=s.MS_CLIENT_SECRET,
        authority=authority,
    )


def build_authorize_url(state: str) -> str:
    s = get_settings()
    authority = f"https://login.microsoftonline.com/{s.MS_TENANT_ID or 'common'}"
    params = {
        "client_id": s.MS_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": s.MS_REDIRECT_URI,
        "response_mode": "query",
        "scope": " ".join(SCOPES) + " offline_access",
        "state": state,
        "prompt": "select_account",
    }
    return f"{authority}/oauth2/v2.0/authorize?{urlencode(params)}"


def new_state_token() -> str:
    return secrets.token_urlsafe(32)


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    scope: str | None


def _bundle_from_msal_result(result: dict) -> TokenBundle:
    if "access_token" not in result:
        err = result.get("error_description") or result.get("error") or "unknown OAuth error"
        raise MsGraphError(f"Microsoft token exchange failed: {err}")
    expires_in = int(result.get("expires_in", 3600))
    return TokenBundle(
        access_token=result["access_token"],
        refresh_token=result.get("refresh_token"),
        expires_at=_utcnow() + timedelta(seconds=max(60, expires_in - 60)),
        scope=result.get("scope"),
    )


def exchange_code(code: str) -> TokenBundle:
    s = get_settings()
    app = _msal_app()
    result = app.acquire_token_by_authorization_code(
        code,
        scopes=list(SCOPES),
        redirect_uri=s.MS_REDIRECT_URI,
    )
    return _bundle_from_msal_result(result)


def refresh_account_token(db: Session, account: MicrosoftAccount) -> MicrosoftAccount:
    if not account.refresh_token:
        raise MsGraphError("No refresh token stored; user must reconnect Microsoft account")
    app = _msal_app()
    result = app.acquire_token_by_refresh_token(account.refresh_token, scopes=list(SCOPES))
    bundle = _bundle_from_msal_result(result)
    account.access_token = bundle.access_token
    if bundle.refresh_token:
        account.refresh_token = bundle.refresh_token
    account.token_expires_at = bundle.expires_at
    if bundle.scope:
        account.scope = bundle.scope
    db.commit()
    db.refresh(account)
    return account


def get_account_for_user(db: Session, user: User) -> MicrosoftAccount | None:
    return db.query(MicrosoftAccount).filter(MicrosoftAccount.user_id == user.id).one_or_none()


def require_account(db: Session, user: User) -> MicrosoftAccount:
    acct = get_account_for_user(db, user)
    if not acct:
        raise MsNotConnectedError("Microsoft account not connected")
    if acct.token_expires_at <= _utcnow():
        acct = refresh_account_token(db, acct)
    return acct


def upsert_account(
    db: Session,
    user: User,
    bundle: TokenBundle,
    me: dict[str, Any],
) -> MicrosoftAccount:
    acct = get_account_for_user(db, user)
    if not acct:
        acct = MicrosoftAccount(user_id=user.id, ms_user_id=str(me.get("id") or ""))
        db.add(acct)
    acct.ms_user_id = str(me.get("id") or acct.ms_user_id or "")
    acct.ms_display_name = me.get("displayName")
    acct.ms_user_principal_name = me.get("userPrincipalName") or me.get("mail")
    acct.access_token = bundle.access_token
    if bundle.refresh_token:
        acct.refresh_token = bundle.refresh_token
    acct.token_expires_at = bundle.expires_at
    acct.scope = bundle.scope
    db.commit()
    db.refresh(acct)
    return acct


def _client(account: MicrosoftAccount) -> httpx.Client:
    return httpx.Client(
        base_url=GRAPH_BASE,
        headers={"Authorization": f"Bearer {account.access_token}"},
        timeout=60.0,
    )


def _retry_on_401(db: Session, account: MicrosoftAccount, fn):
    try:
        return fn(account)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            account = refresh_account_token(db, account)
            return fn(account)
        raise


def get_me(access_token: str) -> dict[str, Any]:
    with httpx.Client(base_url=GRAPH_BASE, timeout=30.0) as c:
        r = c.get("/me", headers={"Authorization": f"Bearer {access_token}"})
        r.raise_for_status()
        return r.json()


def list_recent_meetings(db: Session, account: MicrosoftAccount, days: int = 30) -> list[dict[str, Any]]:
    """List recent calendar events that have a Teams join link.

    Returns the events themselves (most useful metadata for the UI). Each event
    has `onlineMeeting.joinUrl` which is the key we use to look up the meeting.
    """
    start = (_utcnow() - timedelta(days=days)).isoformat()
    end = (_utcnow() + timedelta(days=1)).isoformat()

    def _call(acct: MicrosoftAccount) -> list[dict[str, Any]]:
        params = {
            "startDateTime": start,
            "endDateTime": end,
            "$top": "100",
            "$orderby": "start/dateTime desc",
            "$select": "id,subject,start,end,organizer,attendees,onlineMeeting,isOnlineMeeting,webLink",
        }
        with _client(acct) as c:
            r = c.get("/me/calendarview", params=params)
            r.raise_for_status()
            data = r.json()
            items: list[dict[str, Any]] = []
            for ev in data.get("value", []):
                if ev.get("isOnlineMeeting") and (ev.get("onlineMeeting") or {}).get("joinUrl"):
                    items.append(ev)
            return items

    return _retry_on_401(db, account, _call)


def get_online_meeting_by_join_url(db: Session, account: MicrosoftAccount, join_url: str) -> dict[str, Any]:
    def _call(acct: MicrosoftAccount) -> dict[str, Any]:
        with _client(acct) as c:
            r = c.get("/me/onlineMeetings", params={"$filter": f"JoinWebUrl eq '{join_url}'"})
            r.raise_for_status()
            data = r.json()
            arr = data.get("value", [])
            if not arr:
                raise MsGraphError("Online meeting not found for the given join URL")
            return arr[0]

    return _retry_on_401(db, account, _call)


def list_transcripts(db: Session, account: MicrosoftAccount, meeting_id: str) -> list[dict[str, Any]]:
    def _call(acct: MicrosoftAccount) -> list[dict[str, Any]]:
        with _client(acct) as c:
            r = c.get(f"/me/onlineMeetings/{meeting_id}/transcripts")
            if r.status_code == 404:
                return []
            r.raise_for_status()
            return r.json().get("value", [])

    return _retry_on_401(db, account, _call)


def list_recordings(db: Session, account: MicrosoftAccount, meeting_id: str) -> list[dict[str, Any]]:
    def _call(acct: MicrosoftAccount) -> list[dict[str, Any]]:
        with _client(acct) as c:
            r = c.get(f"/me/onlineMeetings/{meeting_id}/recordings")
            if r.status_code == 404:
                return []
            r.raise_for_status()
            return r.json().get("value", [])

    return _retry_on_401(db, account, _call)


def list_attendance_reports(db: Session, account: MicrosoftAccount, meeting_id: str) -> list[dict[str, Any]]:
    def _call(acct: MicrosoftAccount) -> list[dict[str, Any]]:
        with _client(acct) as c:
            r = c.get(f"/me/onlineMeetings/{meeting_id}/attendanceReports")
            if r.status_code == 404:
                return []
            r.raise_for_status()
            return r.json().get("value", [])

    return _retry_on_401(db, account, _call)


def get_attendance_records(
    db: Session, account: MicrosoftAccount, meeting_id: str, report_id: str
) -> list[dict[str, Any]]:
    def _call(acct: MicrosoftAccount) -> list[dict[str, Any]]:
        with _client(acct) as c:
            r = c.get(
                f"/me/onlineMeetings/{meeting_id}/attendanceReports/{report_id}/attendanceRecords"
            )
            r.raise_for_status()
            return r.json().get("value", [])

    return _retry_on_401(db, account, _call)


def fetch_transcript_vtt(db: Session, account: MicrosoftAccount, meeting_id: str, transcript_id: str) -> str:
    def _call(acct: MicrosoftAccount) -> str:
        with _client(acct) as c:
            r = c.get(
                f"/me/onlineMeetings/{meeting_id}/transcripts/{transcript_id}/content",
                params={"$format": "text/vtt"},
            )
            r.raise_for_status()
            return r.text

    return _retry_on_401(db, account, _call)


def download_recording(
    db: Session,
    account: MicrosoftAccount,
    meeting_id: str,
    recording_id: str,
    dest_path: Path,
) -> int:
    """Stream the recording content to dest_path. Returns bytes written."""

    def _call(acct: MicrosoftAccount) -> int:
        url = f"/me/onlineMeetings/{meeting_id}/recordings/{recording_id}/content"
        written = 0
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(
            base_url=GRAPH_BASE,
            headers={"Authorization": f"Bearer {acct.access_token}"},
            timeout=None,
            follow_redirects=True,
        ) as c:
            with c.stream("GET", url) as r:
                r.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
                        written += len(chunk)
        return written

    return _retry_on_401(db, account, _call)


def names_from_attendance(records: Iterable[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for rec in records:
        ident = rec.get("identity") or {}
        name = (ident.get("displayName") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out
