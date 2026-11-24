"""Bake the TV banner and launcher icon: a ringed planet over a starfield.

Outputs (android/app/src/main/res/):
  drawable-xhdpi/tv_banner.png   320x180, planet + "Missions"
  mipmap-*/ic_launcher.png       48 dp, planet on black
"""

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RES = Path(__file__).resolve().parent.parent / "android/app/src/main/res"
DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
SS = 4  # supersampling


def stars(img, n, seed=7):
    rnd = random.Random(seed)
    d = ImageDraw.Draw(img)
    w, h = img.size
    for _ in range(n):
        x, y = rnd.uniform(0, w), rnd.uniform(0, h)
        r = rnd.choice([1, 1, 1, 2]) * SS * 0.4
        v = rnd.randint(110, 255)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(v, v, min(255, v + 20)))


def planet(img, cx, cy, r):
    """Banded planet with a tilted ring, lit from the upper left."""
    w, h = img.size
    body = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(body)
    bands = [(214, 170, 120), (190, 140, 96), (226, 192, 146), (176, 128, 90),
             (220, 182, 136)]
    for i, c in enumerate(bands):
        y0 = cy - r + 2 * r * i / len(bands)
        d.rectangle([cx - r, y0, cx + r, y0 + 2 * r / len(bands) + 1], fill=c)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    # Terminator shading toward the lower right.
    shade = Image.new("L", img.size, 0)
    ImageDraw.Draw(shade).ellipse(
        [cx - r * 0.7, cy - r * 0.75, cx + r * 1.6, cy + r * 1.5], fill=150)
    shade = shade.filter(ImageFilter.GaussianBlur(r * 0.35))
    dark = Image.new("RGBA", img.size, (0, 0, 0, 255))
    body = Image.composite(dark, body, shade)

    ring = Image.new("RGBA", img.size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    for k, a in ((2.05, 200), (1.75, 255)):
        rd.ellipse([cx - r * k, cy - r * k * 0.28, cx + r * k, cy + r * k * 0.28],
                   outline=(236, 220, 190, a), width=max(1, int(r * 0.09)))
    # Back half of the ring sits behind the planet.
    back = ring.copy()
    ImageDraw.Draw(back).rectangle([0, cy, w, h], fill=(0, 0, 0, 0))
    front = ring.copy()
    ImageDraw.Draw(front).rectangle([0, 0, w, cy], fill=(0, 0, 0, 0))
    img.alpha_composite(back)
    img.paste(body, (0, 0), mask)
    img.alpha_composite(front)


def banner():
    W, H = 320 * SS, 180 * SS
    img = Image.new("RGBA", (W, H), (6, 8, 16, 255))
    stars(img, 90)
    planet(img, 72 * SS, 90 * SS, 30 * SS)
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 38 * SS)
    ImageDraw.Draw(img).text((148 * SS, 90 * SS), "Missions", font=font,
                             fill=(240, 242, 248), anchor="lm")
    out = RES / "drawable-xhdpi/tv_banner.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.resize((320, 180), Image.LANCZOS).convert("RGB").save(out)


def icons():
    for name, k in DENSITIES.items():
        px = round(48 * k)
        S = px * SS
        img = Image.new("RGBA", (S, S), (6, 8, 16, 255))
        stars(img, 14, seed=3)
        planet(img, S / 2, S / 2, S * 0.24)
        out = RES / f"mipmap-{name}/ic_launcher.png"
        img.resize((px, px), Image.LANCZOS).convert("RGB").save(out)


if __name__ == "__main__":
    banner()
    icons()
