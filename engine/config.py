from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    cfg: dict
    root: Path = ROOT
    env: dict = field(default_factory=dict)

    @property
    def knowledge_dir(self) -> Path:
        return self.root / "knowledge"

    @property
    def data_dir(self) -> Path:
        d = self.root / "data"
        d.mkdir(exist_ok=True)
        return d

    def facts(self) -> str:
        """facts.md plus the private RESTRICTED_NAMES from .env (kept out of the public repo).
        The writing agents strip this line before anything reaches the model; the guard uses it."""
        text = (self.knowledge_dir / "facts.md").read_text(encoding="utf-8")
        names = self.env.get("RESTRICTED_NAMES", "")
        return text + (f"\n- RESTRICTED-NAMES: {names}\n" if names else "")

    def voice(self) -> str:
        return (self.knowledge_dir / "voice.md").read_text(encoding="utf-8")

    def topics(self) -> list[dict]:
        return yaml.safe_load((self.knowledge_dir / "topics.yaml").read_text(encoding="utf-8")) or []

    def get(self, *keys, default=None):
        node = self.cfg
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node


def load_settings(root: Path | None = None) -> Settings:
    root = root or ROOT
    load_dotenv(root / ".env")
    cfg = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    keys = [
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
        "LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "GITHUB_TOKEN", "RESTRICTED_NAMES",
    ]
    env = {k: (os.environ.get(k) or "").strip() for k in keys}
    return Settings(cfg=cfg, root=root, env=env)
