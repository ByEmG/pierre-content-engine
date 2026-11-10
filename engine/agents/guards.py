"""Deterministic checks that run before the LLM scorer. A failed guard means score 0."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

BANNED_PHRASES = [
    "in today's fast-paced", "we are now in an era", "game-changer", "game changer",
    "thrilled to announce", "humbled", "let's dive in", "dive into", "unlock", "leverage",
    "delve", "revolutionise", "revolutionize", "the future of", "agree?", "thoughts?",
    "in conclusion", "it's not just", "buckle up",
]
STUDENT_WORDS = ["as a student", "final-year", "final year student", "undergraduate", "my degree", "my coursework"]

NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")
HASHTAG_RE = re.compile(r"(?<!\w)#\w+")


@dataclass
class GuardResult:
    ok: bool
    problems: list[str] = field(default_factory=list)


def restricted_names(facts: str) -> list[str]:
    """Names listed after 'never name' on a RESTRICTED line are blocked. Add them as: RESTRICTED-NAMES: a, b"""
    names = []
    for line in facts.splitlines():
        m = re.match(r"\s*-?\s*RESTRICTED-NAMES:\s*(.+)", line)
        if m:
            names += [n.strip() for n in m.group(1).split(",") if n.strip()]
    return names


def numbers_in(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUM_RE.findall(text)}


def check(body: str, facts: str, notes_text: str, quality: dict) -> GuardResult:
    problems: list[str] = []
    low = body.lower()

    if "\u2014" in body or "\u2013" in body:
        problems.append("Contains an em or en dash. Use commas, colons or full stops.")

    for p in BANNED_PHRASES:
        if p in low:
            problems.append(f'Banned phrase: "{p}".')

    for w in STUDENT_WORDS:
        if w in low:
            problems.append(f'Describes me as a student ("{w}"). Describe the work instead.')

    allowed = numbers_in(facts) | numbers_in(notes_text) | {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10"}
    unknown = sorted(n for n in numbers_in(body) if n not in allowed)
    if unknown:
        problems.append(f"Numbers not found in facts or notes: {', '.join(unknown)}. Remove them or add them to facts.md.")

    for name in restricted_names(facts):
        if name.lower() in low:
            problems.append(f'Names a restricted client or person: "{name}".')

    n = len(body)
    if n < quality.get("min_chars", 500):
        problems.append(f"Too short ({n} chars).")
    if n > quality.get("max_chars", 1800):
        problems.append(f"Too long ({n} chars).")

    tags = HASHTAG_RE.findall(body)
    if len(tags) > quality.get("max_hashtags", 3):
        problems.append(f"Too many hashtags ({len(tags)}).")
    if len(EMOJI_RE.findall(body)) > quality.get("max_emoji", 1):
        problems.append("Too many emoji.")

    if re.search(r"kampus[^.\n]{0,80}\b(is live|went live|now live|in production|launched)\b", low):
        problems.append("Kampus is in active build. Do not call it live, launched or in production.")

    return GuardResult(ok=not problems, problems=problems)
