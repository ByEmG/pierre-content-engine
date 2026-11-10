"""LinkedIn posting through the official API (Share on LinkedIn + OpenID Connect products).

Only posts to your own profile, with the w_member_social scope. No scraping, no DMs.
"""
from __future__ import annotations

import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests

from .store import Store, iso, now_utc

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
API = "https://api.linkedin.com"
SCOPES = "openid profile w_member_social"

# Characters that LinkedIn's "little text" commentary format treats as markup.
_RESERVED = re.compile(r"([\\|{}@\[\]()<>#*_~])")


def escape_commentary(text: str) -> str:
    """Escape reserved characters so LinkedIn doesn't cut the post at the first bracket.
    Hashtags at the end are kept as real hashtags."""
    tail_tags = re.search(r"((?:\s#\w+)+)\s*$", text)
    head, tags = (text[: tail_tags.start()], tail_tags.group(1)) if tail_tags else (text, "")
    return _RESERVED.sub(r"\\\1", head) + tags


def auth_url(client_id: str, redirect_uri: str) -> tuple[str, str]:
    state = secrets.token_urlsafe(16)
    q = urlencode({"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri,
                   "scope": SCOPES, "state": state})
    return f"{AUTH_URL}?{q}", state


def exchange_code(store: Store, client_id: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    r = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "client_id": client_id, "client_secret": client_secret,
    }, timeout=30)
    r.raise_for_status()
    tok = r.json()
    me = requests.get(f"{API}/v2/userinfo", headers={"Authorization": f"Bearer {tok['access_token']}"}, timeout=30)
    me.raise_for_status()
    info = me.json()
    store.set("linkedin", {
        "access_token": tok["access_token"],
        "expires_at": iso(now_utc() + timedelta(seconds=int(tok.get("expires_in", 0)))),
        "person_urn": f"urn:li:person:{info['sub']}",
        "name": info.get("name"),
    })
    return info


class LinkedIn:
    def __init__(self, store: Store, api_version: str):
        cred = store.get("linkedin")
        if not cred:
            raise RuntimeError("LinkedIn not connected. Run: python -m engine linkedin-auth")
        self.token = cred["access_token"]
        self.author = cred["person_urn"]
        self.version = api_version

    def _headers(self, json_body: bool = True) -> dict:
        h = {"Authorization": f"Bearer {self.token}", "LinkedIn-Version": self.version,
             "X-Restli-Protocol-Version": "2.0.0"}
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    def upload_image(self, path: str) -> str:
        r = requests.post(f"{API}/rest/images?action=initializeUpload", headers=self._headers(),
                          json={"initializeUploadRequest": {"owner": self.author}}, timeout=30)
        r.raise_for_status()
        v = r.json()["value"]
        with open(path, "rb") as f:
            up = requests.put(v["uploadUrl"], data=f, headers={"Authorization": f"Bearer {self.token}"}, timeout=120)
        up.raise_for_status()
        return v["image"]

    def post(self, text: str, image_path: str | None = None, alt_text: str = "") -> str:
        body = {
            "author": self.author,
            "commentary": escape_commentary(text),
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        if image_path:
            body["content"] = {"media": {"id": self.upload_image(image_path), "altText": alt_text[:4000]}}
        r = requests.post(f"{API}/rest/posts", headers=self._headers(), json=body, timeout=60)
        if r.status_code >= 400:
            raise RuntimeError(f"LinkedIn post failed {r.status_code}: {r.text[:500]}")
        return r.headers.get("x-restli-id", "")


def days_left(store: Store) -> int | None:
    from datetime import datetime
    cred = store.get("linkedin")
    if not cred:
        return None
    return (datetime.fromisoformat(cred["expires_at"]) - now_utc()).days
