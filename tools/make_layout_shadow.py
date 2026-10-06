"""Turn the raw plant layout (assets/layout_raw.jpg) into the faint line-work shadow
used behind the trolley requirements map (assets/layout_shadow.png).

Dark line work becomes opaque, light fills and paper become transparent, and JPEG
noise is dropped. Run again if the layout drawing changes:

    python tools/make_layout_shadow.py
"""
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC, OUT = ROOT / "assets" / "layout_raw.jpg", ROOT / "assets" / "layout_shadow.png"
INK_RGB = (64, 63, 59)


def main() -> None:
    a = np.asarray(Image.open(SRC).convert("RGB")).astype(float)
    lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    ink = np.clip((215 - lum) / 165, 0, 1) ** 0.9
    ink[ink < 0.14] = 0                      # paper, light fills, JPEG noise
    alpha = np.round(ink * 15) * 17          # 16 levels keeps the PNG small
    rgba = np.zeros((*lum.shape, 4), dtype=np.uint8)
    rgba[..., :3] = INK_RGB
    rgba[..., 3] = alpha.astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(OUT, optimize=True)
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
