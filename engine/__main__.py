"""CLI: python -m engine <command>"""
from __future__ import annotations

import argparse
import sys

from .config import load_settings
from .llm import AnthropicLLM, FakeLLM
from .store import Store


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="engine")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="run the Telegram bot and scheduler (use on the server)")
    d = sub.add_parser("draft", help="make one draft and print it")
    d.add_argument("--pillar")
    d.add_argument("--dry-run", action="store_true", help="use the fake model, no API calls")
    n = sub.add_parser("note", help="add a note from the command line")
    n.add_argument("text")
    sub.add_parser("linkedin-auth", help="connect your LinkedIn account (repeat every ~60 days)")
    sub.add_parser("check", help="check keys and connections")
    a = p.parse_args(argv)

    s = load_settings()
    store = Store(s.data_dir / ("dryrun.db" if getattr(a, "dry_run", False) else "engine.db"))

    if a.cmd == "note":
        print("note", store.add_note(a.text, source="cli"))
        return 0

    if a.cmd == "draft":
        from .pipeline import make_draft
        llm = FakeLLM() if a.dry_run else AnthropicLLM(s.env["ANTHROPIC_API_KEY"], s.get("models"), store)
        res = make_draft(s, store, llm, pillar=a.pillar)
        print(f"\n--- draft #{res.draft_id} · {res.pillar} · score {res.score}/100 · passes {res.passes}\n")
        print(res.body)
        print(f"\nimage: {res.image_path}")
        return 0

    if a.cmd == "linkedin-auth":
        from . import linkedin as li
        cid, secret = s.env["LINKEDIN_CLIENT_ID"], s.env["LINKEDIN_CLIENT_SECRET"]
        redirect = s.get("linkedin", "redirect_uri")
        url, state = li.auth_url(cid, redirect)
        print("1. Open this URL, sign in and allow access:\n\n" + url)
        print("\n2. The browser goes to a localhost page that won't load. That's fine.")
        print("   Copy the full address from the address bar and paste it here.\n")
        pasted = input("Address: ").strip()
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(pasted).query)
        if q.get("state", [""])[0] != state:
            print("State mismatch. Start again.")
            return 1
        info = li.exchange_code(store, cid, secret, redirect, q["code"][0])
        print(f"Connected as {info.get('name')}. Token lasts about 60 days; the bot reminds you a week before.")
        return 0

    if a.cmd == "check":
        ok = True
        for k in ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"):
            have = bool(s.env.get(k))
            ok &= have
            print(f"{'OK ' if have else 'MISSING'}  {k}")
        from . import linkedin as li
        left = li.days_left(store)
        print(f"LinkedIn: {'not connected' if left is None else f'{left} days left'}")
        return 0 if ok else 1

    if a.cmd == "run":
        from .app import App
        from .telegram import Telegram
        llm = AnthropicLLM(s.env["ANTHROPIC_API_KEY"], s.get("models"), store)
        tg = Telegram(s.env["TELEGRAM_BOT_TOKEN"], s.env["TELEGRAM_CHAT_ID"])
        App(s, store, llm, tg).run_forever()
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
