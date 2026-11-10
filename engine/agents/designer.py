"""Renders a 1080x1350 image card in the portfolio style (dark, gold accent)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
BG = (7, 7, 7)
INK = (244, 241, 234)
MUTED = (150, 145, 135)
GOLD = (245, 197, 24)
FONTS = Path(__file__).resolve().parents[2] / "assets" / "fonts"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(FONTS / name), size)
    except OSError:
        return ImageFont.load_default(size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def render_card(card_text: str, kicker: str, author: str, site: str, out_path: Path) -> Path:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    for x in range(28, W, 36):            # faint dot grid
        for y in range(28, H, 36):
            d.point((x, y), fill=(30, 30, 30))

    margin = 96
    mono = _font("DejaVuSansMono.ttf", 30)
    d.text((margin, 150), kicker.upper(), font=mono, fill=GOLD)
    d.rectangle((margin, 210, margin + 90, 214), fill=GOLD)

    # largest headline size that fits in the middle block
    for size in range(104, 47, -4):
        head = _font("InterDisplay-Bold.otf", size)
        lines = _wrap(d, card_text, head, W - 2 * margin)
        line_h = int(size * 1.16)
        if len(lines) * line_h <= 720:
            break
    y = max(290, (H - len(lines) * line_h) // 2 - 60)
    for line in lines:
        d.text((margin, y), line, font=head, fill=INK)
        y += line_h

    foot = _font("Inter-Regular.otf", 34)
    d.text((margin, H - 190), author, font=_font("InterDisplay-Bold.otf", 38), fill=INK)
    d.text((margin, H - 135), site, font=foot, fill=MUTED)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path
