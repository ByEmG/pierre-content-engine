"""Long-running service: listens on Telegram, drafts on schedule, posts approved drafts on time."""
from __future__ import annotations

import time
import traceback
from datetime import datetime

from . import linkedin as li
from .config import Settings
from .pipeline import make_draft, rewrite_draft
from .schedule import draft_due, next_slot
from .sources.github import recent_commits
from .store import Store, iso, now_utc
from .telegram import DRAFT_BUTTONS, Telegram, draft_message, transcribe

HELP = (
    "Send me anything you worked on (text or a voice note) and I'll keep it as material.\n\n"
    "/draft  make a draft now\n"
    "/draft client_delivery|safe_ai|explain_simply|build_in_public  draft for one pillar\n"
    "/queue  show scheduled posts\n"
    "/notes  show unused notes\n"
    "/status  token expiry, costs\n"
    "/help  this message"
)


class App:
    def __init__(self, settings: Settings, store: Store, llm, tg: Telegram, log=print):
        self.s, self.store, self.llm, self.tg, self.log = settings, store, llm, tg, log

    # --- drafting -------------------------------------------------------------
    def send_draft(self, pillar: str | None = None) -> None:
        self.tg.send("Working on a draft…")
        gh = []
        if self.s.get("github", "enabled", default=True):
            gh = recent_commits(self.s.get("github", "user"), self.s.env.get("GITHUB_TOKEN", ""))
        res = make_draft(self.s, self.store, self.llm, pillar=pillar, github_lines=gh, log=self.log)
        self._present(res.draft_id)

    def _present(self, draft_id: int) -> None:
        d = self.store.draft(draft_id)
        self.tg.send_photo(d["image_path"])
        self.tg.send(draft_message(d), DRAFT_BUTTONS(draft_id))

    # --- posting --------------------------------------------------------------
    def _taken(self) -> set[datetime]:
        return {datetime.fromisoformat(x) for x in self.store.scheduled_slots() if x}

    def schedule(self, draft_id: int) -> datetime:
        sch = self.s.get("schedule")
        slot = next_slot(now_utc(), sch["post_days"], sch["post_time"], self.s.get("timezone"), self._taken())
        self.store.update_draft(draft_id, status="scheduled", scheduled_for=iso(slot))
        return slot

    def publish(self, draft_id: int) -> None:
        d = self.store.draft(draft_id)
        client = li.LinkedIn(self.store, self.s.get("linkedin", "api_version"))
        urn = client.post(d["body"], d["image_path"], alt_text=d["card_text"] or "")
        self.store.update_draft(draft_id, status="posted", posted_at=iso(now_utc()), linkedin_urn=urn)
        link = f"https://www.linkedin.com/feed/update/{urn}/" if urn else ""
        self.tg.send(f"Posted draft #{draft_id}. {link}")

    def post_due(self) -> None:
        for d in self.store.due_posts(now_utc()):
            try:
                self.publish(d["id"])
            except Exception as e:  # keep it scheduled and tell me
                self.log(traceback.format_exc())
                self.store.update_draft(d["id"], status="approved")
                self.tg.send(f"Could not post draft #{d['id']}: {e}\nTap Approve again once fixed.",
                             DRAFT_BUTTONS(d["id"]))

    # --- telegram handling ----------------------------------------------------
    def handle(self, upd: dict) -> None:
        if "callback_query" in upd:
            cq = upd["callback_query"]
            if str(cq["message"]["chat"]["id"]) != self.tg.chat_id:
                return
            self.tg.answer_callback(cq["id"])
            action, _, sid = cq["data"].partition(":")
            self.on_button(action, int(sid))
            return
        msg = upd.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != self.tg.chat_id:
            return  # ignore strangers
        text = (msg.get("text") or "").strip()
        if msg.get("voice") or msg.get("audio"):
            self.on_voice(msg)
        elif text.startswith("/"):
            self.on_command(text)
        elif text:
            self.on_text(text)

    def on_button(self, action: str, draft_id: int) -> None:
        d = self.store.draft(draft_id)
        if d is None or d["status"] in ("posted", "rejected", "skipped"):
            self.tg.send(f"Draft #{draft_id} is already {d['status'] if d else 'gone'}.")
            return
        if action == "approve":
            slot = self.schedule(draft_id)
            self.tg.send(f"Scheduled draft #{draft_id} for {slot:%a %d %b, %H:%M}.")
        elif action == "now":
            self.publish(draft_id)
        elif action == "skip":
            self.store.update_draft(draft_id, status="skipped")
            self.tg.send(f"Skipped draft #{draft_id}. Send /draft for another.")
        elif action == "rewrite":
            self.store.set("awaiting_feedback", draft_id)
            self.tg.send(f"What should change in draft #{draft_id}? Reply in one message.")

    def on_command(self, text: str) -> None:
        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@")[0]
        if cmd == "/draft":
            pillar = arg.strip() or None
            if pillar and pillar not in self.s.get("pillars"):
                self.tg.send(f"Unknown pillar. Use one of: {', '.join(self.s.get('pillars'))}")
                return
            self.send_draft(pillar)
        elif cmd == "/queue":
            rows = self.store.db.execute(
                "SELECT id, scheduled_for, angle FROM drafts WHERE status='scheduled' ORDER BY scheduled_for").fetchall()
            self.tg.send("\n".join(f"#{r['id']} {r['scheduled_for'][:16]} {r['angle'][:70]}" for r in rows) or "Queue is empty.")
        elif cmd == "/notes":
            rows = self.store.recent_notes(self.s.get("note_window_days", default=21))
            self.tg.send("\n\n".join(f"[{r['id']}] {r['text'][:200]}" for r in rows) or "No unused notes.")
        elif cmd == "/status":
            left = li.days_left(self.store)
            cost = self.store.db.execute(
                "SELECT COALESCE(SUM(input_tokens),0) i, COALESCE(SUM(output_tokens),0) o FROM usage").fetchone()
            self.tg.send(f"LinkedIn token: {'not connected' if left is None else f'{left} days left'}\n"
                         f"Tokens used so far: {cost['i']:,} in / {cost['o']:,} out")
        else:
            self.tg.send(HELP)

    def on_text(self, text: str) -> None:
        waiting = self.store.get("awaiting_feedback")
        if waiting:
            self.store.set("awaiting_feedback", None)
            self.tg.send("Rewriting…")
            res = rewrite_draft(self.s, self.store, self.llm, int(waiting), text)
            self._present(res.draft_id)
            return
        nid = self.store.add_note(text)
        self.tg.send(f"Saved as note {nid}. It will feed the next draft.")

    def on_voice(self, msg: dict) -> None:
        key = self.s.env.get("OPENAI_API_KEY")
        if not key:
            self.tg.send("Voice notes need OPENAI_API_KEY in .env. Send text for now.")
            return
        f = msg.get("voice") or msg.get("audio")
        path = self.tg.download_file(f["file_id"], self.s.data_dir / "voice" / f"{f['file_unique_id']}.ogg")
        text = transcribe(key, path)
        if text:
            self.on_text(text)

    # --- loop -----------------------------------------------------------------
    def tick(self) -> None:
        sch = self.s.get("schedule")
        key = draft_due(now_utc(), sch["post_days"], sch["draft_time"], self.s.get("timezone"))
        if key and self.store.get("last_auto_draft") != key:
            self.store.set("last_auto_draft", key)
            self.send_draft()
        self.post_due()
        left = li.days_left(self.store)
        if left is not None and left <= 7 and self.store.get("token_warned") != left:
            self.store.set("token_warned", left)
            self.tg.send(f"LinkedIn access expires in {left} days. Run: python -m engine linkedin-auth")

    def run_forever(self) -> None:
        self.log("Content engine running.")
        offset = self.store.get("tg_offset")
        while True:
            try:
                for upd in self.tg.updates(offset):
                    offset = upd["update_id"] + 1
                    self.store.set("tg_offset", offset)
                    try:
                        self.handle(upd)
                    except Exception as e:
                        self.log(traceback.format_exc())
                        self.tg.send(f"Error: {e}")
                self.tick()
            except Exception:
                self.log(traceback.format_exc())
                time.sleep(15)
