"""Minimal Telegram Bot API client (long polling, no webhook, so no domain needed)."""
from __future__ import annotations

import json
from pathlib import Path

import requests


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self.file_base = f"https://api.telegram.org/file/bot{token}"
        self.chat_id = str(chat_id)

    def _call(self, method: str, timeout: int = 40, files=None, **params):
        if files:
            r = requests.post(f"{self.base}/{method}", data=params, files=files, timeout=timeout)
        else:
            r = requests.post(f"{self.base}/{method}", json=params, timeout=timeout)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {data}")
        return data["result"]

    def send(self, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> dict:
        params = {"chat_id": self.chat_id, "text": text[:4096], "disable_web_page_preview": True}
        if buttons:
            params["reply_markup"] = {
                "inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]
            }
        return self._call("sendMessage", **params)

    def send_photo(self, path: str, caption: str = "") -> dict:
        with open(path, "rb") as f:
            return self._call("sendPhoto", files={"photo": f}, chat_id=self.chat_id, caption=caption[:1024])

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        self._call("answerCallbackQuery", callback_query_id=callback_id, text=text)

    def updates(self, offset: int | None) -> list[dict]:
        params = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", timeout=45, **params)

    def download_file(self, file_id: str, dest: Path) -> Path:
        info = self._call("getFile", file_id=file_id)
        r = requests.get(f"{self.file_base}/{info['file_path']}", timeout=60)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return dest


def transcribe(openai_key: str, audio: Path) -> str:
    with open(audio, "rb") as f:
        r = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {openai_key}"},
            files={"file": (audio.name, f)},
            data={"model": "whisper-1"},
            timeout=120,
        )
    r.raise_for_status()
    return r.json().get("text", "").strip()


def draft_message(d, score_detail: str | None = None) -> str:
    detail = json.loads(score_detail or d["score_detail"] or "{}")
    crit = detail.get("criteria") or {}
    crit_line = " · ".join(f"{k} {v}" for k, v in crit.items())
    warn = ""
    if detail.get("guard"):
        warn = "\n⚠️ Guard: " + "; ".join(detail["guard"])
    elif d["score"] is not None and d["score"] < 80:
        warn = "\n⚠️ Below threshold after all passes. Read carefully."
    return (
        f"Draft #{d['id']} · {d['pillar']} · score {d['score']}/100\n{crit_line}{warn}\n"
        f"Angle: {d['angle']}\n\n{d['body']}"
    )


DRAFT_BUTTONS = lambda i: [  # noqa: E731
    [("✅ Approve (next slot)", f"approve:{i}"), ("🚀 Post now", f"now:{i}")],
    [("✏️ Rewrite", f"rewrite:{i}"), ("🗑 Skip", f"skip:{i}")],
]
