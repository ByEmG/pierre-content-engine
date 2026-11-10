# pierre-content-engine

A multi-agent pipeline that writes LinkedIn posts **only from my own work**, never from news.
It drafts on a schedule, checks every claim against a knowledge base, scores each draft, and sends
it to me on Telegram. One tap approves it and it posts at the next slot through LinkedIn's official API.

```
 Telegram notes ─┐
 (text or voice) │
 GitHub commits ─┼─► Planner ─► Hook writer ─► Writer ─► Editor ─► Fact guard ─► Scorer ─┐
 Topic bank ─────┘   (pillar      (10 hooks,     (facts +   (AI tells,  (numbers,    (rubric   │
 facts.md            rotation)     best kept)     notes)     dashes)     names,       /100)    │
                                                                         claims)               │
                          ▲                                                                    │
                          └──────────── below 80: fixes sent back (max 3 passes) ◄─────────────┘
                                                                                               │
                                       Designer (1080x1350 card) ─► Telegram: Approve / Post now / Rewrite / Skip
                                                                                               │
                                                                     LinkedIn Posts API at next slot
```

## What makes it trustworthy

| Agent | What it does |
|---|---|
| Planner | Picks the pillar furthest behind its target share, then an angle from fresh notes, GitHub activity or the topic bank. Never repeats a recent angle. |
| Hook writer | Writes 10 opening lines and keeps the best. |
| Writer | Writes from `facts.md` and source notes only. |
| Editor | Cuts AI tells and filler. A deterministic pass removes em and en dashes. |
| Fact guard | Code, not a model. Blocks any number not in the facts or notes, restricted client names, banned phrases, "student" framing, and calling Kampus live. |
| Scorer | Rubric out of 100: hook, proof, clarity, credibility, voice. Any unsupported claim caps the score at 59. |
| Designer | Renders the image card in the portfolio style. |

Restricted names live only in `.env` (`RESTRICTED_NAMES`), never in the repo, and are never sent to the model.
Every model call is logged with token counts (`/status` on Telegram).

## Content pillars (config.yaml)

| Pillar | Share | Proves |
|---|---|---|
| Client delivery | 35% | I can run requirements and a weekly loop with a real client |
| Safe, measured AI | 25% | I design AI around real constraints and measure it |
| Explained simply | 20% | I can make technical things clear to non-technical buyers |
| Building in public | 20% | Hands-on agent engineering, shown honestly |

Schedule: drafts arrive at 18:00 the evening before each post day; posts go live Tue and Thu at 08:30 UK time.

## Feeding it

Send the bot anything you did, as text or a voice note: "Client asked for parent SMS alerts in today's
Kampus meeting, we moved it ahead of timetables." It becomes material for the next draft, and numbers in
it become allowed numbers. Keep `knowledge/facts.md` up to date as projects move on.

Telegram commands: `/draft`, `/draft safe_ai`, `/queue`, `/notes`, `/status`, `/help`.

## Setup

### 1. Telegram bot (5 min)
1. Message **@BotFather** → `/newbot` → copy the token into `TELEGRAM_BOT_TOKEN`.
2. Message **@userinfobot** → copy your id into `TELEGRAM_CHAT_ID`. The bot ignores everyone else.
3. Send your new bot any message once so it can reply to you.

### 2. LinkedIn app (10 min)
1. Go to linkedin.com/developers → Create app. LinkedIn asks for a Company Page to attach it to; use the Afryx Labs page.
2. Products tab: add **Share on LinkedIn** and **Sign In with LinkedIn using OpenID Connect**.
3. Auth tab: add redirect URL `http://localhost:8765/callback`. Copy Client ID and Secret into `.env`.
4. On the server run `python -m engine linkedin-auth`, open the link, allow access, and paste back the
   address the browser lands on (the page itself won't load; that's expected).
   The token lasts about 60 days. The bot warns you a week before; run the same command again.

### 3. Server (free, runs 24/7 with your laptop off)
1. Create an Oracle Cloud account and an **Always Free** Ubuntu VM (VM.Standard.E2.1.Micro is enough).
2. SSH in, then:
   ```bash
   git clone https://github.com/ByEmG/pierre-content-engine && cd pierre-content-engine
   bash deploy/setup_server.sh      # first run creates .env; fill it in, then run again
   .venv/bin/python -m engine linkedin-auth
   sudo systemctl restart content-engine
   ```
3. Logs: `journalctl -u content-engine -f`.

Oracle can reclaim Always Free VMs that stay idle for 7 days. Upgrading the account to Pay As You Go is
widely reported to stop that, and resources within the Always Free limits stay free.

### Try it locally first
```bash
pip install -r requirements.txt
python -m engine draft --dry-run        # fake model, no keys needed
python -m pytest -q                     # 17 tests
python -m engine draft                  # real draft with your Anthropic key
```

## Not included, on purpose
- No AI news or news-jacking.
- No DMs, scraping or comment automation. It only publishes to your own profile through the official API, after you approve.
