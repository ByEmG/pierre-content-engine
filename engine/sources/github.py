"""Recent public commits from your GitHub, as raw material (not as post topics on their own)."""
from __future__ import annotations

import requests


def recent_commits(user: str, token: str = "", limit: int = 15) -> list[str]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(f"https://api.github.com/users/{user}/events/public", headers=headers, timeout=15)
        r.raise_for_status()
    except requests.RequestException:
        return []
    out = []
    for ev in r.json():
        if ev.get("type") != "PushEvent":
            continue
        repo = ev["repo"]["name"]
        for c in ev.get("payload", {}).get("commits", []):
            msg = c.get("message", "").splitlines()[0]
            if msg and not msg.lower().startswith(("merge", "wip")):
                out.append(f"{ev['created_at'][:10]} {repo}: {msg}")
        if len(out) >= limit:
            break
    return out[:limit]
