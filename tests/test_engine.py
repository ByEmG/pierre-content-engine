import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from engine.agents import guards
from engine.agents.writing import clean, facts_for_llm
from engine.app import App
from engine.config import load_settings
from engine.linkedin import escape_commentary
from engine.llm import DEFAULT_FAKE, FakeLLM, extract_json
from engine.pipeline import choose_pillar, make_draft
from engine.schedule import draft_due, next_slot
from engine.store import Store

Q = {"min_chars": 100, "max_chars": 1800, "max_hashtags": 3, "max_emoji": 1}
FACTS = "Team of 15. 16 client meetings. 100% red-flag sensitivity, 85 to 95% accuracy.\n- RESTRICTED-NAMES: Acme Clinic, Dr Who"
LONG = " Plain sentence about weekly demos with the client team." * 3


@pytest.fixture
def settings():
    return load_settings()


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "t.db")


# guards ---------------------------------------------------------------------
def test_guard_passes_clean_post():
    assert guards.check("We ran 16 client meetings with a team of 15." + LONG, FACTS, "", Q).ok


def test_guard_blocks_invented_number():
    g = guards.check("We cut onboarding time by 42% for the client." + LONG, FACTS, "", Q)
    assert not g.ok and any("42" in p for p in g.problems)


def test_guard_allows_number_from_note():
    assert guards.check("We closed 42 tickets this sprint." + LONG, FACTS, "closed 42 tickets", Q).ok


def test_guard_blocks_dash_banned_phrase_student_restricted():
    body = "Thrilled to announce \u2014 as a student I built this for Acme Clinic." + LONG
    probs = " ".join(guards.check(body, FACTS, "", Q).problems)
    for word in ("dash", "thrilled", "student", "Acme Clinic"):
        assert word.lower() in probs.lower()


def test_guard_blocks_kampus_live_claim():
    g = guards.check("Kampus is live for all three schools." + LONG, FACTS, "", Q)
    assert not g.ok


def test_restricted_names_never_reach_the_model():
    assert "Acme" not in facts_for_llm(FACTS)


# editor ---------------------------------------------------------------------
def test_clean_removes_dashes():
    assert clean("Targets \u2014 85\u201395% accuracy") == "Targets, 85 to 95% accuracy"


# llm json -------------------------------------------------------------------
def test_extract_json_from_fenced_reply():
    assert extract_json('Sure!\n```json\n{"a": {"b": "}"}}\n```') == {"a": {"b": "}"}}


# linkedin -------------------------------------------------------------------
def test_escape_commentary_keeps_trailing_hashtags():
    out = escape_commentary("Rules (not AI) decide. @team\n\n#AI #Consulting")
    assert out.startswith("Rules \\(not AI\\) decide. \\@team")
    assert out.endswith("#AI #Consulting")


# schedule -------------------------------------------------------------------
LDN = "Europe/London"


def test_next_slot_skips_taken():
    mon = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)  # Monday
    first = next_slot(mon, ["Tue", "Thu"], "08:30", LDN)
    assert first == datetime(2026, 11, 10, 8, 30, tzinfo=ZoneInfo(LDN))
    second = next_slot(mon, ["Tue", "Thu"], "08:30", LDN, {first})
    assert second.weekday() == 3


def test_draft_due_evening_before_post_day():
    mon_evening = datetime(2026, 11, 9, 18, 30, tzinfo=timezone.utc)
    assert draft_due(mon_evening, ["Tue"], "18:00", LDN) == "2026-11-09"
    assert draft_due(mon_evening.replace(hour=10), ["Tue"], "18:00", LDN) is None


# pipeline -------------------------------------------------------------------
def test_pillar_rotation_prefers_most_behind(settings, store):
    for _ in range(3):
        store.add_draft(pillar="client_delivery", status="posted", angle="x")
    assert choose_pillar(settings, store) != "client_delivery"


def test_pipeline_end_to_end_with_fake(settings, store, tmp_path, monkeypatch):
    monkeypatch.setattr(type(settings), "data_dir", property(lambda s: tmp_path))
    res = make_draft(settings, store, FakeLLM(), pillar="client_delivery", log=lambda *_: None)
    assert res.score >= 80 and res.passes == 1
    assert Path(res.image_path).exists()
    assert "\u2014" not in res.body


def test_pipeline_revises_when_guard_fails(settings, store, tmp_path, monkeypatch):
    monkeypatch.setattr(type(settings), "data_dir", property(lambda s: tmp_path))
    bad = dict(DEFAULT_FAKE["write"], body=DEFAULT_FAKE["write"]["body"] + "\n\nWe cut costs by 73%.")
    llm = FakeLLM({"write": [bad, DEFAULT_FAKE["write"]]})
    res = make_draft(settings, store, llm, pillar="client_delivery", log=lambda *_: None)
    assert res.history[0]["score"] == 0 and "73" in " ".join(res.history[0]["fixes"])
    assert res.passes == 2 and res.score >= 80
    second_write = [u for t, u in llm.calls if t == "write"][1]
    assert "73" in second_write  # the fix was sent back to the writer


def test_unsupported_claim_caps_score(settings, store, tmp_path, monkeypatch):
    monkeypatch.setattr(type(settings), "data_dir", property(lambda s: tmp_path))
    llm = FakeLLM({"score": {"criteria": {"hook": 20, "proof": 25, "clarity": 20, "credibility": 20, "voice": 15},
                             "unsupported_claims": ["The client doubled enrolment"], "fixes": []}})
    res = make_draft(settings, store, llm, pillar="client_delivery", log=lambda *_: None)
    assert res.score == 59 and res.passes == 3  # never reaches threshold, best draft kept


# telegram app ---------------------------------------------------------------
class FakeTG:
    chat_id = "42"

    def __init__(self):
        self.sent = []

    def send(self, text, buttons=None):
        self.sent.append((text, buttons))

    def send_photo(self, path, caption=""):
        self.sent.append(("PHOTO " + path, None))

    def answer_callback(self, *_):
        pass


def test_app_note_approve_and_ignore_strangers(settings, store, tmp_path, monkeypatch):
    monkeypatch.setattr(type(settings), "data_dir", property(lambda s: tmp_path))
    settings.cfg["github"]["enabled"] = False
    tg = FakeTG()
    app = App(settings, store, FakeLLM(), tg, log=lambda *_: None)

    app.handle({"message": {"chat": {"id": 999}, "text": "hack"}})
    assert tg.sent == []

    app.handle({"message": {"chat": {"id": 42}, "text": "Client asked for SMS alerts for parents today"}})
    assert store.recent_notes(30)[0]["text"].startswith("Client asked")

    app.handle({"message": {"chat": {"id": 42}, "text": "/draft client_delivery"}})
    draft_id = store.db.execute("SELECT max(id) m FROM drafts").fetchone()["m"]
    app.handle({"callback_query": {"id": "c", "data": f"approve:{draft_id}", "message": {"chat": {"id": 42}}}})
    assert store.draft(draft_id)["status"] == "scheduled"
    assert "Scheduled" in tg.sent[-1][0]


def test_app_rewrite_flow(settings, store, tmp_path, monkeypatch):
    monkeypatch.setattr(type(settings), "data_dir", property(lambda s: tmp_path))
    settings.cfg["github"]["enabled"] = False
    tg = FakeTG()
    app = App(settings, store, FakeLLM(), tg, log=lambda *_: None)
    app.handle({"message": {"chat": {"id": 42}, "text": "/draft"}})
    first = store.db.execute("SELECT max(id) m FROM drafts").fetchone()["m"]
    app.handle({"callback_query": {"id": "c", "data": f"rewrite:{first}", "message": {"chat": {"id": 42}}}})
    app.handle({"message": {"chat": {"id": 42}, "text": "Shorter, and end with a takeaway"}})
    assert store.draft(first)["status"] == "rejected"
    newest = store.draft(first + 1)
    assert json.loads(newest["score_detail"])["feedback"] == "Shorter, and end with a takeaway"
