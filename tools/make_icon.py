"""Generate assets/island.ico (multi-size icon: black island with an accent dot)."""
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "assets", "island.ico")


def draw(size):
    s = 4  # supersampling for smooth edges
    S = size * s
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # dark rounded Windows 11-style background
    bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle((S * 0.04, S * 0.04, S * 0.96, S * 0.96), radius=S * 0.22, fill=(28, 28, 32, 255))
    img = Image.alpha_composite(img, bg)
    # black pill with a thin border
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = S * 0.14, S * 0.36, S * 0.86, S * 0.64
    d.rounded_rectangle((x0, y0, x1, y1), radius=(y1 - y0) * 0.36, fill=(0, 0, 0, 255),
                        outline=(255, 255, 255, 70), width=max(1, int(S * 0.012)))
    # mini equalizer and accent dot
    cx = S * 0.30
    for i, h in enumerate((0.10, 0.17, 0.12)):
        bx = cx + i * S * 0.055
        d.rounded_rectangle((bx, S * 0.5 - S * h / 2, bx + S * 0.03, S * 0.5 + S * h / 2), radius=S * 0.015,
                            fill=(255, 255, 255, 235))
    r = S * 0.055
    d.ellipse((S * 0.72 - r, S * 0.5 - r, S * 0.72 + r, S * 0.5 + r), fill=(76, 194, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


os.makedirs(os.path.dirname(OUT), exist_ok=True)
sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
imgs = [draw(n) for n in sizes]
imgs[-1].save(OUT, format="ICO", sizes=[(n, n) for n in sizes], append_images=imgs[:-1])
imgs[-1].save(os.path.join(HERE, "assets", "island.png"))
print("icon:", OUT, os.path.getsize(OUT), "bytes")
