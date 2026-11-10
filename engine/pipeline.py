"""The full draft pipeline: plan, hook, write, edit, guard, score, revise, design."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .agents import guards
from .agents.designer import render_card
from .agents.writing import clean, edit, facts_for_llm, hooks, plan, score, write
from .config import Settings
from .llm import LLM
from .store import Store


@dataclass
class DraftResult:
    draft_id: int
    pillar: str
    angle: str
    body: str
    score: int
    passes: int
    image_path: str
    history: list[dict] = field(default_factory=list)
    guard_problems: list[str] = field(default_factory=list)


def choose_pillar(settings: Settings, store: Store) -> str:
    """Pick the pillar furthest behind its target share over the last 60 days."""
    weights: dict = settings.get("pillars")
    rows = store.drafts_since(60, ("approved", "scheduled", "posted"))
    counts = {p: 0 for p in weights}
    for r in rows:
        if r["pillar"] in counts:
            counts[r["pillar"]] += 1
    total = sum(counts.values()) + 1
    deficits = {p: weights[p] * total - counts[p] for p in weights}
    return max(deficits, key=lambda p: (deficits[p], weights[p]))


def available_topics(settings: Settings, store: Store, pillar: str) -> list[dict]:
    cooldown = settings.get("topic_cooldown_days", default=60)
    used = {r["topic_id"] for r in store.drafts_since(cooldown, ("pending", "approved", "scheduled", "posted"))}
    return [t for t in settings.topics() if t["pillar"] == pillar and t["id"] not in used]


def make_draft(settings: Settings, store: Store, llm: LLM, *, pillar: str | None = None,
               github_lines: list[str] | None = None, log=print) -> DraftResult:
    pillar = pillar or choose_pillar(settings, store)
    label = settings.get("pillar_labels", pillar, default=pillar)
    q = settings.get("quality")
    raw_facts = settings.facts()
    facts = facts_for_llm(raw_facts)
    voice = settings.voice()

    notes = [dict(n) for n in store.recent_notes(settings.get("note_window_days", default=21))]
    recent = [r["angle"] for r in store.drafts_since(90, ("pending", "approved", "scheduled", "posted")) if r["angle"]]

    log(f"[planner] pillar={pillar}")
    angle = plan(llm, facts=facts, voice=voice, pillar=pillar, pillar_label=label,
                 topics=available_topics(settings, store, pillar), notes=notes,
                 github=github_lines or [], recent_angles=recent)
    used_ids = [int(i) for i in angle.get("note_ids") or []]
    notes_text = "\n".join(n["text"] for n in notes if n["id"] in used_ids) if used_ids else \
        "\n".join(n["text"] for n in notes)
    log(f"[planner] angle: {angle['angle']}")

    hook = hooks(llm, angle=angle, facts=facts, voice=voice)
    log(f"[hooks] chose: {hook}")

    history: list[dict] = []
    best: dict | None = None
    draft, fixes = None, None
    for n in range(1, q["max_passes"] + 1):
        draft = write(llm, angle=angle, hook=hook, facts=facts, voice=voice, notes_text=notes_text,
                      previous=draft["body"] if draft else None, fixes=fixes)
        draft["body"] = clean(draft["body"])
        draft = edit(llm, draft=draft, voice=voice)

        g = guards.check(draft["body"], raw_facts, notes_text, q)
        if g.ok:
            s = score(llm, body=draft["body"], facts=facts, voice=voice, notes_text=notes_text)
        else:
            s = {"score": 0, "criteria": {}, "unsupported_claims": [], "fixes": g.problems}
        s["guard_problems"] = g.problems
        history.append({"pass": n, "score": s["score"], "fixes": s["fixes"]})
        log(f"[scorer] pass {n}: {s['score']}/100" + (f" guard: {g.problems}" if g.problems else ""))

        if best is None or s["score"] > best["s"]["score"]:
            best = {"draft": dict(draft), "s": s, "n": n}
        if s["score"] >= q["threshold"]:
            break
        fixes = s["fixes"] or ["Make it more specific and more useful to the reader."]

    final, s = best["draft"], best["s"]
    draft_id = store.add_draft(
        pillar=pillar, topic_id=angle.get("topic_id"), note_ids=used_ids, angle=angle["angle"], hook=hook,
        body=final["body"], card_text=final.get("card_text") or hook, score=s["score"],
        score_detail={"criteria": s["criteria"], "fixes": s["fixes"], "guard": s["guard_problems"], "history": history},
        passes=len(history), status="pending",
    )
    img = render_card(final.get("card_text") or hook, label, settings.get("author", "name"),
                      settings.get("author", "site"), settings.data_dir / "cards" / f"draft_{draft_id}.png")
    store.update_draft(draft_id, image_path=str(img))
    store.mark_notes_used(used_ids)
    return DraftResult(draft_id, pillar, angle["angle"], final["body"], s["score"], len(history), str(img),
                       history, s["guard_problems"])


def rewrite_draft(settings: Settings, store: Store, llm: LLM, draft_id: int, feedback: str) -> DraftResult:
    """Rewrite an existing draft with Pierre's feedback, then guard and score again."""
    row = store.draft(draft_id)
    q = settings.get("quality")
    raw_facts = settings.facts()
    facts, voice = facts_for_llm(raw_facts), settings.voice()
    ids = json.loads(row["note_ids"] or "[]")
    notes_text = "\n".join(
        r["text"] for r in store.db.execute(
            f"SELECT text FROM notes WHERE id IN ({','.join('?' * len(ids)) or 'NULL'})", ids
        ).fetchall()
    )
    angle = {"angle": row["angle"]}
    draft = write(llm, angle=angle, hook=row["hook"], facts=facts, voice=voice, notes_text=notes_text,
                  previous=row["body"], feedback=feedback)
    draft["body"] = clean(draft["body"])
    draft = edit(llm, draft=draft, voice=voice)
    g = guards.check(draft["body"], raw_facts, notes_text, q)
    s = score(llm, body=draft["body"], facts=facts, voice=voice, notes_text=notes_text) if g.ok else \
        {"score": 0, "criteria": {}, "fixes": g.problems}
    new_id = store.add_draft(
        pillar=row["pillar"], topic_id=row["topic_id"], note_ids=ids, angle=row["angle"], hook=row["hook"],
        body=draft["body"], card_text=draft.get("card_text") or row["card_text"], score=s["score"],
        score_detail={"criteria": s.get("criteria"), "fixes": s.get("fixes"), "guard": g.problems,
                      "feedback": feedback, "rewrite_of": draft_id},
        passes=1, status="pending",
    )
    store.update_draft(draft_id, status="rejected")
    label = settings.get("pillar_labels", row["pillar"], default=row["pillar"])
    img = render_card(draft.get("card_text") or row["card_text"], label, settings.get("author", "name"),
                      settings.get("author", "site"), settings.data_dir / "cards" / f"draft_{new_id}.png")
    store.update_draft(new_id, image_path=str(img))
    return DraftResult(new_id, row["pillar"], row["angle"], draft["body"], s["score"], 1, str(img), [], g.problems)
