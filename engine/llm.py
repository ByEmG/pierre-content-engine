"""LLM access. Every agent asks for JSON back through complete_json()."""
from __future__ import annotations

import json
import re
from typing import Callable, Protocol


class LLM(Protocol):
    def complete_json(self, task: str, system: str, user: str, model_key: str = "writer") -> dict: ...


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply, tolerating code fences and prose."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object in reply: {text[:200]}")
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("Unbalanced JSON in reply")


class AnthropicLLM:
    def __init__(self, api_key: str, models: dict, store=None):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.models = models
        self.store = store

    def complete_json(self, task: str, system: str, user: str, model_key: str = "writer") -> dict:
        model = self.models.get(model_key) or self.models["writer"]
        last_err = None
        for _ in range(2):
            msg = self.client.messages.create(
                model=model,
                max_tokens=2500,
                system=system + "\n\nReply with one JSON object only. No prose before or after it.",
                messages=[{"role": "user", "content": user}],
            )
            if self.store is not None:
                self.store.log_usage(task, model, msg.usage.input_tokens, msg.usage.output_tokens)
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            try:
                return extract_json(text)
            except (ValueError, json.JSONDecodeError) as e:
                last_err = e
        raise RuntimeError(f"{task}: model did not return valid JSON ({last_err})")


class FakeLLM:
    """Deterministic stand-in for tests and --dry-run. Responses keyed by task name."""

    def __init__(self, responses: dict[str, Callable[[str, str], dict] | dict | list] | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, task: str, system: str, user: str, model_key: str = "writer") -> dict:
        self.calls.append((task, user))
        r = self.responses.get(task, DEFAULT_FAKE.get(task))
        if r is None:
            raise KeyError(f"FakeLLM has no response for task {task!r}")
        if isinstance(r, list):  # pop in sequence, keep last
            return r.pop(0) if len(r) > 1 else r[0]
        return r(system, user) if callable(r) else r


DEFAULT_FAKE: dict = {
    "plan": {
        "angles": [
            {
                "angle": "16 client meetings on Kampus taught me the gap between what a client asks for and what they need.",
                "material": "Kampus weekly client loop, 3 Fang institutions",
                "why_credible": "Shows requirements work with a real client.",
            }
        ]
    },
    "hooks": {
        "hooks": [
            {"text": "16 client meetings. The best feature request was never the first one.", "score": 9},
            {"text": "Clients rarely ask for what they need.", "score": 6},
        ]
    },
    "write": {
        "body": (
            "16 client meetings in, one habit matters more than any feature.\n\n"
            "On Kampus, we build school management software for Fang, a private education group in Cameroon with 3 institutions.\n\n"
            "Each institution needs its own tailored software. One client, three sets of needs.\n\n"
            "So we never try to get the spec right in one go. Every week we run the same loop:\n\n"
            "1. Demo what we built\n"
            "2. Capture what changed and what is missing\n"
            "3. Reprioritise with the team of 15\n"
            "4. Present the next version\n\n"
            "The client sees progress every week, and we hear about a wrong assumption within days, not months.\n\n"
            "A spec is a guess. A weekly demo is how you check it.\n\n"
            "How often do you put working software in front of your clients?"
        ),
        "card_text": "A spec is a guess. A weekly demo is how you check it.",
    },
    "edit": lambda system, user: {"body": json.loads(user.split("DRAFT JSON:\n", 1)[1])["body"]},
    "score": {
        "score": 86,
        "criteria": {"hook": 17, "proof": 22, "clarity": 18, "credibility": 17, "voice": 12},
        "fixes": [],
    },
}
