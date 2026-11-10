"""Planner, hook writer, writer, editor and scorer agents."""
from __future__ import annotations

import json
import re

from ..llm import LLM


def facts_for_llm(facts: str) -> str:
    """Never send restricted names to the model."""
    return "\n".join(l for l in facts.splitlines() if "RESTRICTED-NAMES:" not in l)


GROUND_RULES = (
    "You write LinkedIn posts for Pierre Ankouane from his own work only. "
    "Use only facts from FACTS and SOURCE NOTES. Never invent events, conversations, quotes, numbers, "
    "clients or results. If the material has no specific moment, write from the facts as they stand. "
    "Never write about AI news or other companies."
)


# Planner ------------------------------------------------------------------
def plan(llm: LLM, *, facts: str, voice: str, pillar: str, pillar_label: str,
         topics: list[dict], notes: list[dict], github: list[str], recent_angles: list[str]) -> dict:
    system = GROUND_RULES + " You are the planner: pick what this post should be about."
    user = (
        f"PILLAR: {pillar_label}\n\n"
        f"FACTS:\n{facts}\n\n"
        f"SOURCE NOTES (recent, from Pierre; prefer these, they are fresh):\n"
        + ("\n".join(f"[note {n['id']}] {n['text']}" for n in notes) or "(none)")
        + "\n\nRECENT GITHUB ACTIVITY:\n" + ("\n".join(github) or "(none)")
        + "\n\nTOPIC BANK for this pillar:\n" + ("\n".join(f"[{t['id']}] {t['idea']}" for t in topics) or "(none)")
        + "\n\nANGLES ALREADY USED RECENTLY (do not repeat):\n" + ("\n".join(recent_angles) or "(none)")
        + "\n\nPropose up to 3 angles for one post in this pillar, best first. Each angle must be backed by the "
        "facts or notes above and must help a hiring manager for Solutions Engineer, Implementation Engineer or "
        "Technology Consultant roles trust Pierre with clients.\n"
        'JSON: {"angles": [{"angle": str, "topic_id": str|null, "note_ids": [int], '
        '"material": str, "why_credible": str}]}'
    )
    out = llm.complete_json("plan", system, user, "writer")
    if not out.get("angles"):
        raise RuntimeError("Planner returned no angles")
    return out["angles"][0]


# Hook writer --------------------------------------------------------------
def hooks(llm: LLM, *, angle: dict, facts: str, voice: str) -> str:
    system = GROUND_RULES + " You are the hook writer."
    user = (
        f"ANGLE: {angle['angle']}\nMATERIAL: {angle.get('material', '')}\n\nFACTS:\n{facts}\n\nVOICE:\n{voice}\n\n"
        "Write 10 opening lines (max 120 characters each) for this post. Concrete beats clever. "
        "No questions as hooks, no clickbait, no em dashes. Score each 1 to 10 for how likely a busy hiring "
        "manager stops scrolling AND still trusts the writer.\n"
        'JSON: {"hooks": [{"text": str, "score": int}]}'
    )
    out = llm.complete_json("hooks", system, user, "fast")
    ranked = sorted(out.get("hooks", []), key=lambda h: h.get("score", 0), reverse=True)
    if not ranked:
        raise RuntimeError("Hook writer returned nothing")
    return ranked[0]["text"]


# Writer -------------------------------------------------------------------
def write(llm: LLM, *, angle: dict, hook: str, facts: str, voice: str, notes_text: str,
          previous: str | None = None, fixes: list[str] | None = None, feedback: str | None = None) -> dict:
    system = GROUND_RULES + " You are the writer."
    parts = [
        f"ANGLE: {angle['angle']}", f"OPENING LINE (use it as the first line): {hook}",
        f"FACTS:\n{facts}", f"SOURCE NOTES:\n{notes_text or '(none)'}", f"VOICE RULES:\n{voice}",
    ]
    if previous:
        parts.append(f"PREVIOUS DRAFT:\n{previous}")
    if fixes:
        parts.append("FIX ALL OF THESE:\n" + "\n".join(f"- {f}" for f in fixes))
    if feedback:
        parts.append(f"PIERRE'S FEEDBACK (highest priority):\n{feedback}")
    parts.append(
        "Write the full post, 700 to 1500 characters. Also write card_text: one line of max 12 words, "
        "the single idea of the post, for the image.\n"
        'JSON: {"body": str, "card_text": str}'
    )
    return llm.complete_json("write", system, "\n\n".join(parts), "writer")


# Editor -------------------------------------------------------------------
def clean(text: str) -> str:
    """Deterministic clean-up that runs after every model pass."""
    text = re.sub(r"\s*\u2014\s*", ", ", text)          # em dash -> comma
    text = re.sub(r"(\d)\s*\u2013\s*(\d)", r"\1 to \2", text)  # 85\u201395 -> 85 to 95
    text = re.sub(r"\s*\u2013\s*", ", ", text)
    text = text.replace("\u201c", '"').replace("\u201d", '"').replace("\u2019", "'")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def edit(llm: LLM, *, draft: dict, voice: str) -> dict:
    system = (
        "You are a strict editor. Cut AI tells, filler, hype and repetition. Keep every fact and number exactly "
        "as written. Do not add new claims. Keep the first line. UK spelling. No em dashes."
    )
    user = f"VOICE RULES:\n{voice}\n\nReturn the edited post as JSON {{\"body\": str}}.\n\nDRAFT JSON:\n" + json.dumps(
        {"body": draft["body"]}
    )
    out = llm.complete_json("edit", system, user, "fast")
    return {**draft, "body": clean(out.get("body") or draft["body"])}


# Scorer -------------------------------------------------------------------
RUBRIC = (
    "hook (0-20): would a busy hiring manager stop and read?\n"
    "proof (0-25): specific, real work and results from FACTS or NOTES, not generic advice\n"
    "clarity (0-20): a non-technical client could follow it\n"
    "credibility (0-20): makes Pierre look trustworthy for client-facing technical roles; no hype\n"
    "voice (0-15): follows VOICE RULES, no AI tells"
)


def score(llm: LLM, *, body: str, facts: str, voice: str, notes_text: str) -> dict:
    system = "You are a tough LinkedIn editor and fact checker. Score honestly; 80+ means ready to publish."
    user = (
        f"FACTS:\n{facts}\n\nSOURCE NOTES:\n{notes_text or '(none)'}\n\nVOICE RULES:\n{voice}\n\nPOST:\n{body}\n\n"
        f"Score with this rubric:\n{RUBRIC}\n\n"
        "List every claim in the post that FACTS or NOTES do not support as an unsupported claim. "
        "If there is any unsupported claim, the total must be below 60.\n"
        'JSON: {"criteria": {"hook": int, "proof": int, "clarity": int, "credibility": int, "voice": int}, '
        '"unsupported_claims": [str], "fixes": [str]}'
    )
    out = llm.complete_json("score", system, user, "fast")
    crit = out.get("criteria", {})
    total = sum(int(crit.get(k, 0)) for k in ("hook", "proof", "clarity", "credibility", "voice"))
    if "score" in out and not crit:
        total = int(out["score"])
    claims = out.get("unsupported_claims") or []
    if claims:
        total = min(total, 59)
    fixes = list(out.get("fixes") or []) + [f"Remove or support: {c}" for c in claims]
    return {"score": total, "criteria": crit, "unsupported_claims": claims, "fixes": fixes}
