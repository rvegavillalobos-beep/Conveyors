"""Trolley requirements by station - schematic plant map rendered as a single SVG.

Coordinates are in the space of the plant layout drawing (approx. 1100 x 660 units).
The map is a simplified schematic: cluster zones, access gates for orientation, every
docking station (the ones where Production requested a trolley highlighted), the support
areas and, optionally, the real conveyor layout as a faint background.
Docking positions come from colour detection on the flags-only layout, registered to this
coordinate space. Edit the data blocks below to update the graphic.
"""
from __future__ import annotations

import base64
from html import escape
from pathlib import Path

# ----------------------------------------------------------------------------- data
CLUSTERS = {
    "C": {"color": "#e34948", "ink": "#ffffff",
          "zone": [(152, 72), (816, 72), (816, 190), (152, 190)], "label": (246, 92)},
    "E": {"color": "#eda100", "ink": "#2b1f00",
          "zone": [(816, 72), (973, 72), (973, 320), (482, 320), (482, 190), (816, 190)],
          "label": (560, 240)},
    "H": {"color": "#eb6834", "ink": "#ffffff",
          "zone": [(152, 190), (482, 190), (482, 320), (350, 320), (350, 633), (152, 633)],
          "label": (198, 340)},
    "F": {"color": "#d55181", "ink": "#ffffff",
          "zone": [(350, 320), (705, 320), (705, 633), (350, 633)], "label": (372, 340)},
    "P": {"color": "#2a78d6", "ink": "#ffffff",
          "zone": [(705, 320), (973, 320), (973, 633), (705, 633)], "label": (862, 336)},
}

# Docking stations where a trolley was requested (one trolley each): cluster, x, y, station flag.
DOCKING_POINTS = [
    ("C", 655, 170, "759"), ("C", 815, 163, "789"),
    ("E", 588, 296, "809"), ("E", 906, 160, "719"),
    ("H", 389, 202, "859"), ("H", 351, 253, "729"), ("H", 170, 508, "979"),
    ("F", 615, 346, "739 / 759"), ("F", 626, 529, "749"), ("F", 679, 548, "769"),
    ("F", 703, 574, "789"), ("F", 351, 593, "719"),
    ("P", 843, 428, None), ("P", 948, 446, "819"), ("P", 743, 486, "729"), ("P", 942, 492, "769"),
    ("P", 774, 525, "799"), ("P", 857, 568, "749"), ("P", 923, 598, "759"),
]

# Docking stations on the layout where no trolley was requested.
UNUSED_POINTS = [
    ("C", 160, 89, "719"), ("C", 700, 103, "769"), ("C", 757, 178, "77"),
    ("E", 836, 122, "709"), ("E", 496, 199, "829"), ("E", 547, 202, "819"), ("E", 639, 214, "779"),
    ("E", 724, 214, "759"), ("E", 512, 273, "839"), ("E", 834, 278, "72"), ("E", 639, 304, "789"),
    ("E", 724, 306, "769"),
    ("H", 273, 198, "829"), ("H", 221, 212, None), ("H", 476, 218, "719"), ("H", 237, 283, "789"),
    ("H", 238, 426, "909"), ("H", 336, 433, "879"), ("H", 311, 473, "949"), ("H", 243, 511, "969"),
    ("H", 219, 590, "989"),
    ("F", 651, 500, "739"), ("F", 514, 615, "729"),
    ("P", 742, 372, "719"), ("P", 899, 490, "789"), ("P", 885, 558, "779"), ("P", 749, 608, "739"),
]

# Support areas outside the production floor: key, label, trolleys, box, accent.
SUPPORT_AREAS = [
    {"key": "S", "name": "Scrap center", "trolleys": 10, "box": (34, 176, 106, 132),
     "color": "#4a3aa7", "tint": "#eeecf8"},
    {"key": "R", "name": "Rework", "sub": "Secondary function rooms", "trolleys": 2,
     "box": (152, 6, 430, 46), "color": "#52514e", "tint": "#f0efea"},
    {"key": "Q", "name": "Quality hub", "sub": "Q-HUB", "trolleys": 2, "box": (986, 158, 102, 106),
     "color": "#52514e", "tint": "#f0efea"},
]

# Access gates / workpiece carriers, for orientation only: label, x, y, w, h, vertical.
GATES = [
    ("WPC1 (TS04)", 192, 86, 33, 66, True), ("WPC2 (TS08)", 155, 196, 28, 116, True),
    ("TS01", 742, 85, 66, 25, False), ("TS02", 826, 85, 70, 25, False),
    ("TS03", 413, 281, 69, 21, False), ("WPC3 (TS09)", 753, 347, 99, 21, False),
    ("TS05", 235, 608, 81, 24, False), ("TS06", 561, 594, 100, 23, False),
]

PLANT = (150, 70, 825, 565)  # x, y, w, h

# Real conveyor layout as a faint background (see tools/make_layout_shadow.py).
# Placement comes from registering the raw drawing to this coordinate space.
SHADOW_FILE = Path(__file__).resolve().parent / "assets" / "layout_shadow.png"
SHADOW_PLACEMENT = (139.25, 39.80, 1117 * 0.7592, 779 * 0.7592)  # x, y, w, h
SHADOW_OPACITY = 0.30
SELECTION_NOTE = ("Trolleys sit where NOK parts can no longer move forward: "
                  "the downstream stations are not built to pass scrap")

# Map views, from least to most detail. Every view keeps the same positions and styling;
# each one only adds a layer on top of the previous one.
VIEWS = {
    "requested": "Requested only",   # requested stations + support areas
    "stations": "All stations",      # + docking stations without a request
    "layout": "Full layout",         # + real conveyor layout as background
}

# ----------------------------------------------------------------------------- style
FONT = "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
INK, INK2, MUTED, LINE = "#0b0b0b", "#52514e", "#898781", "#d9d8d1"
CANVAS_W, CANVAS_H = 1560, 760
MAP_DX, MAP_DY = 14, 78          # where the plant drawing sits on the canvas
PANEL_X, PANEL_W = 1144, 370     # right-hand summary panel


def cluster_counts() -> dict:
    counts = {k: 0 for k in CLUSTERS}
    for key, *_ in DOCKING_POINTS:
        counts[key] += 1
    return counts


def totals() -> dict:
    counts = cluster_counts()
    clusters = sum(counts.values())
    support = sum(a["trolleys"] for a in SUPPORT_AREAS)
    stations = len(DOCKING_POINTS) + len(UNUSED_POINTS)
    return {"clusters": clusters, "support": support, "total": clusters + support, "by_cluster": counts,
            "stations": stations}


def _shadow_href() -> str | None:
    if not SHADOW_FILE.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(SHADOW_FILE.read_bytes()).decode("ascii")


def _t(x, y, text, size=12, weight=400, fill=INK, anchor="start", extra=""):
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}" {extra}>{escape(str(text))}</text>')


def _chip(x, y, size, color, ink, letter, radius=6):
    return (f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="{radius}" fill="{color}"/>'
            + _t(x + size / 2, y + size / 2 + size * 0.17, letter, size * 0.5, 700, ink, "middle"))


def build_svg(view: str = "layout") -> str:
    if view not in VIEWS:
        raise ValueError(f"view must be one of {list(VIEWS)}, got {view!r}")
    show_unused = view != "requested"
    tot = totals()
    counts = tot["by_cluster"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS_W} {CANVAS_H}" '
           f'width="100%" role="img" aria-label="Trolley requirements by station" '
           f'style="font-family:{FONT};display:block">']
    out.append(f'<title>Trolley requirements by station: {tot["total"]} trolleys</title>')
    out.append('<defs>'
               '<pattern id="tr-grid" width="41" height="41" patternUnits="userSpaceOnUse">'
               '<circle cx="1" cy="1" r="1" fill="#e4e3dc"/></pattern>'
               '<filter id="tr-shadow" x="-20%" y="-20%" width="140%" height="160%">'
               '<feDropShadow dx="0" dy="1.5" stdDeviation="2" flood-color="#0b0b0b" flood-opacity="0.18"/>'
               '</filter>'
               f'<clipPath id="tr-plant"><rect x="{PLANT[0]}" y="{PLANT[1]}" width="{PLANT[2]}" '
               f'height="{PLANT[3]}" rx="10"/></clipPath>'
               '<marker id="tr-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
               'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#a9a79f"/></marker>'
               '</defs>')
    out.append(f'<rect width="{CANVAS_W}" height="{CANVAS_H}" fill="#ffffff"/>')

    # ---- heading
    out.append(_t(40, 44, "Trolley requirements by station", 26, 700, INK, extra='letter-spacing="-0.4"'))
    out.append(_t(40, 68, SELECTION_NOTE, 14, 400, INK2))

    # ---- map
    g = [f'<g transform="translate({MAP_DX},{MAP_DY})">']
    px, py, pw, ph = PLANT
    g.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="10" fill="#fbfbfa" stroke="#c3c2b7" '
             f'stroke-width="1.4"/>')
    shadow = _shadow_href() if view == "layout" else None
    if not shadow:
        g.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="10" fill="url(#tr-grid)"/>')
    for key, c in CLUSTERS.items():
        pts = " ".join(f"{x},{y}" for x, y in c["zone"])
        g.append(f'<polygon points="{pts}" fill="{c["color"]}" fill-opacity="{0.11 if shadow else 0.13}" '
                 f'stroke="#ffffff" stroke-width="4" stroke-linejoin="round"/>')
    if shadow:
        sx, sy, sw, sh = SHADOW_PLACEMENT
        g.append(f'<image href="{shadow}" x="{sx:.2f}" y="{sy:.2f}" width="{sw:.2f}" height="{sh:.2f}" '
                 f'opacity="{SHADOW_OPACITY}" preserveAspectRatio="none" clip-path="url(#tr-plant)"/>')
    for key, c in CLUSTERS.items():  # zone outlines on top of the white gaps, very light
        pts = " ".join(f"{x},{y}" for x, y in c["zone"])
        g.append(f'<polygon points="{pts}" fill="none" stroke="{c["color"]}" stroke-opacity="0.35" '
                 f'stroke-width="1" stroke-linejoin="round"/>')

    # gates
    for label, x, y, w, h, vertical in GATES:
        g.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" fill="#4a4945"/>')
        if vertical:
            cx, cy = x + w / 2, y + h / 2
            g.append(_t(cx, cy + 3.5, label, 9.5, 500, "#ffffff", "middle",
                        f'transform="rotate(-90 {cx} {cy})"'))
        else:
            g.append(_t(x + w / 2, y + h / 2 + 3.5, label, 9.5, 500, "#ffffff", "middle"))

    # docking stations without a request: quiet, hollow
    for key, x, y, flag in (UNUSED_POINTS if show_unused else []):
        tip = f"Cluster {key} docking station" + (f" · flag {flag}" if flag else "") + " · no trolley requested"
        g.append(f'<g><title>{escape(tip)}</title>'
                 f'<circle cx="{x}" cy="{y}" r="7.5" fill="#ffffff" stroke="#9b9990" stroke-width="1.6"/>'
                 + _t(x, y + 3, key, 8, 700, "#8a887f", "middle") + '</g>')

    # cluster labels
    for key, c in CLUSTERS.items():
        lx, ly = c["label"]
        n = counts[key]
        g.append(f'<rect x="{lx - 6}" y="{ly - 6}" width="118" height="38" rx="8" fill="#ffffff" '
                 f'fill-opacity="0.88" filter="url(#tr-shadow)"/>')
        g.append(_chip(lx, ly, 26, c["color"], c["ink"], key))
        g.append(_t(lx + 34, ly + 11, f"Cluster {key}", 12.5, 650, INK))
        g.append(_t(lx + 34, ly + 25, f"{n} trolley{'s' if n != 1 else ''}", 11.5, 400, INK2))

    # docking points
    for key, x, y, flag in DOCKING_POINTS:
        c = CLUSTERS[key]
        tip = f"Cluster {key} docking point" + (f" · flag {flag}" if flag else "") + " · 1 trolley"
        g.append(f'<g><title>{escape(tip)}</title>'
                 f'<circle cx="{x}" cy="{y}" r="17" fill="{c["color"]}" fill-opacity="0.22"/>'
                 f'<circle cx="{x}" cy="{y}" r="10.5" fill="{c["color"]}" stroke="#ffffff" stroke-width="2.5"/>'
                 + _t(x, y + 4, key, 11, 700, c["ink"], "middle") + '</g>')

    # support areas
    for a in SUPPORT_AREAS:
        x, y, w, h = a["box"]
        n = a["trolleys"]
        g.append(f'<g><title>{escape(a["name"])}: {n} trolleys</title>')
        g.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{a["tint"]}" '
                 f'stroke="{a["color"]}" stroke-width="{1.8 if a["key"] == "S" else 1.1}"/>')
        if a["key"] == "R":  # wide, short box above the plant
            g.append(_chip(x + 10, y + 10, 26, a["color"], "#ffffff", a["key"]))
            g.append(_t(x + 46, y + 21, a["name"], 13, 650, INK))
            g.append(_t(x + 46, y + 36, a["sub"], 11, 400, INK2))
            g.append(f'<rect x="{x + w - 108}" y="{y + 9}" width="98" height="28" rx="14" fill="{a["color"]}"/>')
            g.append(_t(x + w - 59, y + 28, f"{n} trolleys", 13, 700, "#ffffff", "middle"))
        else:
            cx = x + w / 2
            g.append(_t(cx, y + 22, a["name"].upper(), 10, 700, a["color"], "middle", 'letter-spacing="0.8"'))
            if a.get("sub"):
                g.append(_t(cx, y + 36, a["sub"], 10.5, 400, INK2, "middle"))
            g.append(_t(cx, y + h - 34, n, 40 if a["key"] == "S" else 34, 700, a["color"] if a["key"] == "S"
                        else INK, "middle", 'letter-spacing="-1"'))
            g.append(_t(cx, y + h - 16, "trolleys", 11.5, 500, INK2, "middle"))
        g.append('</g>')
    # connectors from the building to the support areas (approximate locations)
    g.append(f'<path d="M150,254 L142,254" stroke="#a9a79f" stroke-width="1.6" '
             f'stroke-dasharray="3 3" marker-end="url(#tr-arrow)"/>')
    g.append(f'<path d="M975,211 L984,211" stroke="#a9a79f" stroke-width="1.6" '
             f'stroke-dasharray="3 3" marker-end="url(#tr-arrow)"/>')
    g.append(f'<path d="M300,70 L300,54" stroke="#a9a79f" stroke-width="1.6" '
             f'stroke-dasharray="3 3" marker-end="url(#tr-arrow)"/>')
    # scrap call-out tag
    g.append(f'<rect x="34" y="316" width="106" height="22" rx="11" fill="#4a3aa7"/>')
    g.append(_t(87, 331, "Largest need", 10.5, 650, "#ffffff", "middle"))
    g.append('</g>')
    out.extend(g)

    # ---- summary panel
    x0, w = PANEL_X, PANEL_W
    out.append(f'<rect x="{x0 - 22}" y="92" width="{w + 44}" height="{CANVAS_H - 112}" rx="16" fill="#f7f6f3"/>')
    out.append(_t(x0, 128, "TOTAL REQUIRED", 11, 700, MUTED, extra='letter-spacing="1.2"'))
    out.append(_t(x0 - 3, 196, tot["total"], 72, 700, INK, extra='letter-spacing="-3"'))
    out.append(_t(x0 + 92, 196, "trolleys", 20, 500, INK2))
    out.append(_t(x0, 222, "Requirements aligned with Production", 13, 400, INK2))

    # split: clusters vs support areas
    split_y = 246
    cw = w * tot["clusters"] / tot["total"]
    out.append(f'<rect x="{x0}" y="{split_y}" width="{cw - 2}" height="10" rx="5" fill="#184f95"/>')
    out.append(f'<rect x="{x0 + cw}" y="{split_y}" width="{w - cw}" height="10" rx="5" fill="#4a3aa7"/>')
    for col, (n, line1, line2, color) in enumerate((
            (tot["clusters"], "at docking stations",
             f"of {tot['stations']} stations, 5 clusters" if show_unused else "in 5 production clusters",
             "#184f95"),
            (tot["support"], "at support areas", "Scrap, Rework, Quality", "#4a3aa7"))):
        cx = x0 + col * (w / 2 + 20)
        out.append(f'<circle cx="{cx + 5}" cy="{split_y + 30}" r="5" fill="{color}"/>')
        out.append(_t(cx + 16, split_y + 37, n, 22, 700, INK))
        out.append(_t(cx + 48, split_y + 37, line1, 12.5, 400, INK2))
        out.append(_t(cx + 16, split_y + 56, line2, 12.5, 400, INK2))

    # ranked list
    rows = [(a["name"], a["key"], a["trolleys"], a["color"], "#ffffff") for a in SUPPORT_AREAS]
    rows += [(f"Cluster {k}", k, counts[k], c["color"], c["ink"]) for k, c in CLUSTERS.items()]
    order = {"S": 0, "P": 1, "F": 2, "H": 3, "C": 4, "E": 5, "R": 6, "Q": 7}
    rows.sort(key=lambda r: (-r[2], order.get(r[1], 9)))
    top = max(r[2] for r in rows)
    list_y = 352
    out.append(f'<line x1="{x0}" y1="{list_y - 30}" x2="{x0 + w}" y2="{list_y - 30}" stroke="{LINE}"/>')
    out.append(_t(x0, list_y - 8, "BY STATION", 11, 700, MUTED, extra='letter-spacing="1.2"'))
    bar_x, bar_w = x0 + 136, w - 136 - 70
    row_h = 37
    for i, (name, key, n, color, ink) in enumerate(rows):
        y = list_y + 12 + i * row_h
        out.append(_chip(x0, y, 24, color, ink, key))
        out.append(_t(x0 + 34, y + 17, name, 13.5, 500, INK))
        out.append(f'<rect x="{bar_x}" y="{y + 8}" width="{bar_w}" height="8" rx="4" fill="#e9e8e2"/>')
        out.append(f'<rect x="{bar_x}" y="{y + 8}" width="{max(bar_w * n / top, 8)}" height="8" rx="4" '
                   f'fill="{color}"/>')
        out.append(_t(x0 + w - 34, y + 18, n, 15, 700, INK, "end"))
        out.append(_t(x0 + w, y + 18, f"{n / tot['total']:.0%}", 11.5, 400, MUTED, "end"))
    total_y = list_y + 12 + len(rows) * row_h + 6
    out.append(f'<line x1="{x0}" y1="{total_y}" x2="{x0 + w}" y2="{total_y}" stroke="{INK}" stroke-width="1"/>')
    out.append(_t(x0 + 34, total_y + 24, "Total", 13.5, 700, INK))
    out.append(_t(x0 + w - 34, total_y + 24, tot["total"], 15, 700, INK, "end"))
    out.append(_t(x0 + w, total_y + 24, "100%", 11.5, 400, MUTED, "end"))

    # legend under the map (items only for the layers on screen; spacing stays the same)
    ly = MAP_DY + PLANT[1] + PLANT[3] + 30
    x = MAP_DX + PLANT[0]
    items = [("requested", "Trolley requested (1 per station)", 252),
             ("unused", "Docking station, not requested", 224),
             ("support", "Support area (approx. location)", 236),
             ("gate", "Access / WPC", 0)]
    for kind, label, width in items:
        if kind == "unused" and not show_unused:
            continue
        if kind == "requested":
            out.append(f'<circle cx="{x + 10}" cy="{ly}" r="13" fill="#2a78d6" fill-opacity="0.22"/>'
                       f'<circle cx="{x + 10}" cy="{ly}" r="8" fill="#2a78d6" stroke="#ffffff" stroke-width="2"/>')
            out.append(_t(x + 30, ly + 4.5, label, 12, 400, INK2))
        elif kind == "unused":
            out.append(f'<circle cx="{x}" cy="{ly}" r="7" fill="#ffffff" stroke="#9b9990" stroke-width="1.6"/>')
            out.append(_t(x + 16, ly + 4.5, label, 12, 400, INK2))
        elif kind == "support":
            out.append(f'<rect x="{x}" y="{ly - 9}" width="26" height="18" rx="5" fill="#f0efea" '
                       f'stroke="#52514e" stroke-width="1"/>')
            out.append(_t(x + 34, ly + 4.5, label, 12, 400, INK2))
        else:
            out.append(f'<rect x="{x}" y="{ly - 9}" width="26" height="18" rx="3" fill="#4a4945"/>')
            out.append(_t(x + 34, ly + 4.5, label, 12, 400, INK2))
        x += width
    out.append('</svg>')
    return "".join(out)


if __name__ == "__main__":  # quick local preview
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "requirements_map.svg"
    view = sys.argv[2] if len(sys.argv) > 2 else "layout"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build_svg(view))
    print(totals())
