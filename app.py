"""Trolley capacity ramp-up - scenario planner.

Streamlit app that compares the capacity of the outfeed/infeed trolley fleet
against production demand week by week, including incoming trolley shipments,
mechanical adjustment of new trolleys, the year-end shutdown and scrap build-up.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import astuple, dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402
from matplotlib.transforms import blended_transform_factory  # noqa: E402

import importlib  # noqa: E402

import requirements_map  # noqa: E402

# Streamlit keeps imported modules in memory across reruns; reload so a redeploy
# always picks up the current requirements_map.py without rebooting the app.
requirements_map = importlib.reload(requirements_map)

APP_DIR = Path(__file__).parent

# =============================================================================
# Model constants
# =============================================================================
TRANSIT_WEEKS = 4                 # fixed sea transit
HOURS_PER_WEEK = 45.0             # production hours per week
DAYS_PER_WEEK = 5.0
UPH_AT_TARGET = 30                # "Trolleys required for 30 UPH"
SHUTDOWN_WEEKS = ("CW52", "CW1")  # year-end shutdown (no production)
HORIZON_END = "CW13"              # chart always runs at least to this week
PRODUCTION_START = "CW45"         # chart always starts at least here (first production week)

# Planning calendar: CW42 2026 onwards. Kept long so readiness of late batches
# can still be computed even when it falls beyond the visible horizon.
CALENDAR = [(f"CW{w}", 2026) for w in range(42, 53)] + [(f"CW{w}", 2027) for w in range(1, 53)]
WEEK_LABELS = [w for w, _ in CALENDAR]

# Weekly production demand (units / week). Shutdown weeks are 0.
DEMAND_UNITS_PER_WEEK = {
    "CW45": 65, "CW46": 49, "CW47": 69, "CW48": 123, "CW49": 147, "CW50": 184, "CW51": 196,
    "CW52": 0, "CW1": 0, "CW2": 176, "CW3": 199, "CW4": 223, "CW5": 246,
    "CW6": 206, "CW7": 270, "CW8": 281,
}
# Calendar index -> demand (first occurrence of each label = planning year).
DEMAND_BY_IDX = {WEEK_LABELS.index(w): v for w, v in DEMAND_UNITS_PER_WEEK.items()}
FIRST_DATA_IDX = min(DEMAND_BY_IDX)
LAST_DATA_IDX = max(DEMAND_BY_IDX)

SHIP_WEEK_OPTIONS = [f"CW{i}" for i in range(42, 53)] + [f"CW{i}" for i in range(1, 14)]

UNIT_OPTIONS = ["UPH (Units / Hour)", "Units / Week", "Units / Day"]
UNIT_CFG = {
    "UPH (Units / Hour)": {"short": "UPH", "cap_factor": 1.0, "demand_div": HOURS_PER_WEEK, "decimals": 1},
    "Units / Week": {"short": "units/week", "cap_factor": HOURS_PER_WEEK, "demand_div": 1.0, "decimals": 0},
    "Units / Day": {"short": "units/day", "cap_factor": HOURS_PER_WEEK / DAYS_PER_WEEK,
                    "demand_div": DAYS_PER_WEEK, "decimals": 0},
}

SCRAP_MODES = [
    "Until the first batch arrives",
    "Until the first batch is fully operational",
    "Custom CW range",
]

# =============================================================================
# Visual system
# =============================================================================
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE, SURFACE = "#ecebe6", "#c3c2b7", "#ffffff"
BLUE, ORANGE, VIOLET = "#2a78d6", "#eb6834", "#4a3aa7"      # capacity / demand / scrap
NAVY, PENDING = "#184f95", "#86b6ef"                        # operational / pending trolleys
CRITICAL = "#d03b3b"                                        # shortfall (status)
SHUTDOWN_FILL, NODATA_FILL = "#f0efea", "#f8f7f4"
TRANSIT_FILL, CUSTOMS_FILL = "#f6e2ae", "#eda100"
OUT_OF_WINDOW = "#dad8d1"
CAP_TEXT, DEM_TEXT = "#1c5cab", "#a8461d"                   # darker steps for value labels

FIG_W = 14.0
LEFT, RIGHT = 0.078, 0.905

_fonts = sorted((APP_DIR / "assets" / "fonts").glob("*.otf"))
for _font in _fonts:
    font_manager.fontManager.addfont(str(_font))
plt.rcParams.update({
    "font.family": "Inter" if _fonts else "DejaVu Sans",
    "font.size": 9,
    "axes.titlesize": 11,
    "text.color": INK,
    "axes.labelcolor": INK2,
    "svg.fonttype": "none",
})


# =============================================================================
# Scenario model
# =============================================================================
@dataclass(frozen=True)
class Params:
    unit_mode: str
    label_all: bool
    base_fleet: int
    trolleys_for_30: int
    rate: int
    adjust_in_shutdown: bool
    shutdown_rate: int
    b1_qty: int
    b1_ship: str
    b1_customs: int
    b2_qty: int
    b2_ship: str
    b2_customs: int
    scrap_on: bool
    scrap_pct: float
    scrap_mode: str
    scrap_range: tuple


@dataclass
class Batch:
    name: str
    qty: int
    ship_idx: int
    customs: int
    arrival_idx: int
    ready_idx: int | None = None

    @property
    def ship_label(self) -> str:
        return WEEK_LABELS[self.ship_idx]

    @property
    def arrival_label(self) -> str:
        return WEEK_LABELS[self.arrival_idx]

    @property
    def ready_label(self) -> str:
        return WEEK_LABELS[self.ready_idx] if self.ready_idx is not None else "after CW52"


def build_scenario(p: Params) -> dict:
    unit = UNIT_CFG[p.unit_mode]
    n_cal = len(CALENDAR)

    batches = []
    for name, qty, ship, customs in (("Batch 1", p.b1_qty, p.b1_ship, p.b1_customs),
                                     ("Batch 2", p.b2_qty, p.b2_ship, p.b2_customs)):
        s = WEEK_LABELS.index(ship)
        batches.append(Batch(name, qty, s, customs, s + TRANSIT_WEEKS + customs))

    # ---- Fleet simulation (whole calendar, so late readiness is still known) ----
    arrivals = np.zeros(n_cal, dtype=int)
    for b in batches:
        arrivals[b.arrival_idx] += b.qty

    physical = np.zeros(n_cal, dtype=int)
    operational = np.zeros(n_cal, dtype=int)
    cur_p = cur_o = p.base_fleet
    for i, (week, _) in enumerate(CALENDAR):
        cur_p += arrivals[i]
        if week in SHUTDOWN_WEEKS:
            step = p.shutdown_rate if p.adjust_in_shutdown else 0
        else:
            step = p.rate
        if cur_o < cur_p:
            cur_o = min(cur_p, cur_o + step)
        physical[i], operational[i] = cur_p, cur_o

    # Adjustment is first-in-first-out: a batch is ready once every trolley that
    # arrived up to (and including) it has been adjusted.
    cumulative = p.base_fleet
    for b in sorted(batches, key=lambda b: (b.arrival_idx, b.name)):
        cumulative += b.qty
        ready = np.nonzero((np.arange(n_cal) >= b.arrival_idx) & (operational >= cumulative))[0]
        b.ready_idx = int(ready[0]) if ready.size else None

    # ---- Visible horizon ----
    start = min(WEEK_LABELS.index(PRODUCTION_START), *(b.ship_idx for b in batches))
    end = max(WEEK_LABELS.index(HORIZON_END), *(b.arrival_idx for b in batches))
    idx = list(range(start, end + 1))

    weeks = [WEEK_LABELS[i] for i in idx]
    years = [CALENDAR[i][1] for i in idx]
    phys = physical[start:end + 1]
    op = operational[start:end + 1]
    cap = op / float(p.trolleys_for_30) * UPH_AT_TARGET * unit["cap_factor"]
    demand_units = [DEMAND_BY_IDX.get(i) for i in idx]
    demand = [None if d is None else d / unit["demand_div"] for d in demand_units]
    scrap_modules = [None if d is None else d * p.scrap_pct / 100.0 for d in demand_units]
    scrap_conv = [None if d is None else d * p.scrap_pct / 100.0 for d in demand]

    # ---- Capacity vs demand ----
    prod_weeks = [k for k, d in enumerate(demand_units) if d]  # weeks with production > 0
    headroom = {k: cap[k] - demand[k] for k in prod_weeks}
    short_weeks = [k for k in prod_weeks if headroom[k] < 0]
    tight_k = min(prod_weeks, key=lambda k: headroom[k]) if prod_weeks else None
    ref_k = LAST_DATA_IDX - start  # last week with demand data (CW8)

    # ---- Scrap accumulation window ----
    first_batch = min(batches, key=lambda b: (b.arrival_idx, b.name))
    capped = False
    if p.scrap_mode == SCRAP_MODES[0]:
        w_start, w_end = FIRST_DATA_IDX, first_batch.arrival_idx - 1
        why = f"before {first_batch.name} arrives ({first_batch.arrival_label})"
    elif p.scrap_mode == SCRAP_MODES[1]:
        w_start = FIRST_DATA_IDX
        w_end = (first_batch.ready_idx - 1) if first_batch.ready_idx is not None else n_cal - 1
        why = f"until {first_batch.name} is fully operational ({first_batch.ready_label})"
    else:
        a, b_ = (WEEK_LABELS.index(w) for w in p.scrap_range)
        w_start, w_end = min(a, b_), max(a, b_)
        why = "selected range"
    if w_end > LAST_DATA_IDX:
        w_end, capped = LAST_DATA_IDX, True
    window = [i for i in range(max(w_start, FIRST_DATA_IDX), w_end + 1)]
    window_produced = sum(DEMAND_BY_IDX.get(i, 0) for i in window)
    window_total = window_produced * p.scrap_pct / 100.0
    window_k = [i - start for i in window if start <= i <= end]

    sd_text = (f"adjusting {p.shutdown_rate}/wk during shutdown" if p.adjust_in_shutdown
               else "no adjustment during shutdown")

    return {
        "p": p, "unit": unit, "batches": batches, "first_batch": first_batch,
        "weeks": weeks, "years": years, "phys": phys, "op": op, "cap": cap,
        "demand_units": demand_units, "demand": demand,
        "scrap_modules": scrap_modules, "scrap_conv": scrap_conv,
        "prod_weeks": prod_weeks, "headroom": headroom, "short_weeks": short_weeks,
        "tight_k": tight_k, "ref_k": ref_k, "sd_text": sd_text,
        "window": window, "window_k": window_k, "window_total": window_total,
        "window_produced": window_produced, "window_why": why, "window_capped": capped,
    }


# =============================================================================
# Formatting helpers
# =============================================================================
def fmt(value: float, decimals: int) -> str:
    return f"{value:,.{decimals}f}"


def fmt_signed(value: float, decimals: int) -> str:
    return ("+" if value >= 0 else "−") + fmt(abs(value), decimals)


def week_range(idx_list: list) -> str:
    if not idx_list:
        return "–"
    a, b = WEEK_LABELS[idx_list[0]], WEEK_LABELS[idx_list[-1]]
    return a if a == b else f"{a}–{b}"


def text_pts(text: str, size: float) -> float:
    """Rough rendered width of a string in points (Inter averages ~0.56 em)."""
    return len(text) * size * 0.56


# =============================================================================
# Charts
# =============================================================================
def _style_axis(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.spines["bottom"].set_linewidth(0.9)
    ax.tick_params(axis="both", colors=MUTED, labelsize=8.5, length=0, pad=6)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _panel_header(ax, title: str, handles: list) -> None:
    ax.text(0, 1.04, title, transform=ax.transAxes, fontsize=11, fontweight=600,
            color=INK, ha="left", va="bottom")
    if handles:
        ax.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=len(handles),
                  frameon=False, fontsize=8.8, handlelength=1.7, handleheight=0.9,
                  columnspacing=1.5, handletextpad=0.55, labelcolor=INK2, borderaxespad=0.2)


def _shade_shutdown(axes, weeks, label_ax=None, note=None) -> None:
    ks = [k for k, w in enumerate(weeks) if w in SHUTDOWN_WEEKS]
    if not ks:
        return
    k0, k1 = min(ks), max(ks)
    for ax in axes:
        ax.axvspan(k0 - 0.5, k1 + 0.5, color=SHUTDOWN_FILL, zorder=0, lw=0)
    if label_ax is not None:
        tr = blended_transform_factory(label_ax.transData, label_ax.transAxes)
        label_ax.text((k0 + k1) / 2, 0.975, "Shutdown", transform=tr, ha="center", va="top",
                      fontsize=8.5, fontweight=600, color=INK2, zorder=6)
        if note:
            label_ax.text((k0 + k1) / 2, 0.915, note, transform=tr, ha="center", va="top",
                          fontsize=7.6, color=MUTED, zorder=6)


def _week_axis(ax, weeks, years) -> None:
    ax.set_xticks(np.arange(len(weeks)))
    ax.set_xticklabels(weeks, fontsize=8.3)
    ax.tick_params(axis="x", labelcolor=INK2)
    ax.set_xlim(-0.5, len(weeks) - 0.5)
    seen = set()
    for k, y in enumerate(years):
        if y not in seen:
            seen.add(y)
            ax.annotate(str(y), xy=(k - 0.4, 0), xycoords=("data", "axes fraction"),
                        xytext=(0, -26), textcoords="offset points", ha="left", va="top",
                        fontsize=8.5, fontweight=600, color=INK2, annotation_clip=False)


def _to_png(fig, dpi: int = 200) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=SURFACE)
    plt.close(fig)
    return buf.getvalue()


def draw_main_chart(s: dict) -> bytes:
    p, unit = s["p"], s["unit"]
    dec, u = unit["decimals"], unit["short"]
    weeks, n = s["weeks"], len(s["weeks"])
    x = np.arange(n)
    cap, op, phys = s["cap"], s["op"], s["phys"]

    fig = plt.figure(figsize=(FIG_W, 9.2), facecolor=SURFACE)
    gs = fig.add_gridspec(3, 1, height_ratios=[3.1, 1.6, 0.95], hspace=0.5,
                          left=LEFT, right=RIGHT, top=0.95, bottom=0.08)
    ax_a = fig.add_subplot(gs[0])
    ax_b = fig.add_subplot(gs[1], sharex=ax_a)
    ax_c = fig.add_subplot(gs[2], sharex=ax_a)
    for ax in (ax_a, ax_b, ax_c):
        _style_axis(ax)
    # Week labels sit right under the capacity panel (and again under the shipments),
    # and a hairline per week lets the eye drop from each point to its CW.
    ax_a.tick_params(labelbottom=True)
    ax_b.tick_params(labelbottom=False)
    ax_a.grid(axis="x", color=GRID, linewidth=0.7)

    sd_note = f"adjusting {p.shutdown_rate}/wk" if p.adjust_in_shutdown else "adjustment paused"
    _shade_shutdown((ax_a, ax_b, ax_c), weeks, label_ax=ax_a, note=sd_note)

    # ================= Panel A: capacity vs demand =================
    mask = np.array([d is not None for d in s["demand"]])
    xd = x[mask]
    dem = np.array([d for d in s["demand"] if d is not None], dtype=float)
    cap_d = cap[mask]
    scrap = np.array([d for d in s["scrap_conv"] if d is not None], dtype=float)

    ref_k = s["ref_k"]
    if ref_k < n - 1:
        ax_a.axvspan(ref_k + 0.5, n - 0.5, color=NODATA_FILL, zorder=0, lw=0)
        tr = blended_transform_factory(ax_a.transData, ax_a.transAxes)
        ax_a.text((ref_k + 0.5 + n - 0.5) / 2, 0.975, f"No demand data after {weeks[ref_k]}",
                  transform=tr, ha="center", va="top", fontsize=8.2, color=MUTED, zorder=6)

    has_short = bool(s["short_weeks"])
    if has_short:
        ax_a.fill_between(xd, cap_d, dem, where=dem > cap_d, interpolate=True,
                          color=CRITICAL, alpha=0.16, lw=0, zorder=1)

    line_kw = dict(linewidth=2.2, markersize=5.6, markeredgecolor=SURFACE, markeredgewidth=1.4,
                   solid_capstyle="round", solid_joinstyle="round")
    ax_a.plot(x, cap, color=BLUE, marker="o", markerfacecolor=BLUE, zorder=4, **line_kw)
    ax_a.plot(xd, dem, color=ORANGE, marker="o", markerfacecolor=ORANGE, zorder=5, **line_kw)
    if p.scrap_on:
        ax_a.plot(xd, scrap, color=VIOLET, marker="D", markerfacecolor=VIOLET, zorder=5,
                  **{**line_kw, "markersize": 4.6, "linewidth": 1.8})

    y_top = max(cap.max(), dem.max() if dem.size else 0) * 1.28 or 1
    # With every point labeled, leave a strip under zero so the lowest labels never hit the axis.
    y_bottom = -0.09 * y_top if p.label_all else 0.0
    ax_a.set_ylim(y_bottom, y_top)
    ax_a.set_yticks([t for t in MaxNLocator(5).tick_values(0, y_top) if 0 <= t <= y_top])
    ax_a.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    if y_bottom < 0:
        ax_a.spines["bottom"].set_visible(False)
        ax_a.axhline(0, color=BASELINE, linewidth=0.9, zorder=1)

    px = fig.dpi / 72.0  # pixels per point

    def y_px(xv, yv):
        return ax_a.transData.transform((xv, yv))[1]

    # ---- End labels; stacked apart when two series end on the same week ----
    sdec = 1 if dec else 0
    ends = [(n - 1, cap[-1], f"Capacity {fmt(cap[-1], dec)}")]
    if xd.size:
        ends.append((xd[-1], dem[-1], f"Demand {fmt(dem[-1], dec)}"))
        if p.scrap_on:
            ends.append((xd[-1], scrap[-1], f"Scrap {fmt(scrap[-1], sdec)}"))
    for xv in {e[0] for e in ends}:
        floor = None
        for _, yv, text in sorted((e for e in ends if e[0] == xv), key=lambda e: e[1]):
            natural = y_px(xv, yv)
            target = natural if floor is None else max(natural, floor + 14 * px)
            floor = target
            ax_a.annotate(text, (xv, yv), xytext=(9, (target - natural) / px), textcoords="offset points",
                          ha="left", va="center", fontsize=9, fontweight=600, color=INK, zorder=8,
                          annotation_clip=False,
                          bbox=dict(boxstyle="round,pad=0.18", fc=SURFACE, ec="none", alpha=0.9))

    if p.label_all:
        # Per week: the highest series is labeled above its point, the lowest below, and
        # the one in the middle goes to whichever side has more room (or to the right if
        # neither side has room). Labels never face each other, so they can't collide.
        series = [(list(cap), lambda v: fmt(v, dec), CAP_TEXT, {n - 1}),
                  (s["demand"], lambda v: fmt(v, dec), DEM_TEXT, {ref_k})]
        if p.scrap_on:
            series.append((s["scrap_conv"], lambda v: fmt(v, sdec), VIOLET, {ref_k}))
        room = (7.6 + 5) * px + 3
        placements = {"up": dict(xytext=(0, 4.5), ha="center", va="bottom"),
                      "down": dict(xytext=(0, -4.5), ha="center", va="top"),
                      "right": dict(xytext=(7, 0), ha="left", va="center")}
        for k in range(n):
            pts = sorted(((v, y_px(k, v), fmt_fn(v), color)
                          for vals, fmt_fn, color, skip in series
                          for v in [vals[k]] if v is not None and v > 0 and k not in skip),
                         key=lambda t: -t[1])
            for i, (v, ypix, text, color) in enumerate(pts):
                if i == 0:
                    side = "up"
                elif i == len(pts) - 1:
                    side = "down"
                else:
                    gap_up, gap_down = pts[i - 1][1] - ypix, ypix - pts[i + 1][1]
                    side = ("right" if max(gap_up, gap_down) < room
                            else "up" if gap_up >= gap_down else "down")
                ax_a.annotate(text, (k, v), textcoords="offset points", fontsize=7.6, fontweight=600,
                              color=color, zorder=7,
                              bbox=dict(boxstyle="round,pad=0.12", fc=SURFACE, ec="none", alpha=0.85),
                              **placements[side])
    else:
        # One call-out: the tightest week (or the worst shortfall).
        k = s["tight_k"]
        if k is not None:
            hr = s["headroom"][k]
            color = CRITICAL if hr < 0 else INK2
            ax_a.annotate("", xy=(k, cap[k]), xytext=(k, s["demand"][k]),
                          arrowprops=dict(arrowstyle="<->", color=color, lw=1.1, shrinkA=5, shrinkB=5),
                          zorder=6)
            title = "Largest shortfall" if hr < 0 else "Tightest week"
            ax_a.annotate(f"{title} · {weeks[k]}\n{fmt_signed(hr, dec)} {u}",
                          ((k), (cap[k] + s["demand"][k]) / 2), xytext=(-10, 0),
                          textcoords="offset points", ha="right", va="center", fontsize=8.6,
                          color=INK, zorder=7, linespacing=1.35,
                          bbox=dict(boxstyle="round,pad=0.3", fc=SURFACE, ec="none", alpha=0.92))

    handles_a = [
        Line2D([0], [0], color=BLUE, lw=2.2, marker="o", ms=5.5, mfc=BLUE, mec=SURFACE, label="Trolley capacity"),
        Line2D([0], [0], color=ORANGE, lw=2.2, marker="o", ms=5.5, mfc=ORANGE, mec=SURFACE,
               label="Production demand"),
    ]
    if p.scrap_on:
        handles_a.append(Line2D([0], [0], color=VIOLET, lw=1.8, marker="D", ms=4.5, mfc=VIOLET, mec=SURFACE,
                                label=f"Scrap ({p.scrap_pct:g}%)"))
    if has_short:
        handles_a.append(Patch(facecolor=CRITICAL, alpha=0.16, label="Shortfall"))
    _panel_header(ax_a, f"Capacity vs. production demand  ·  {u}", handles_a)

    # ================= Panel B: trolley fleet =================
    pending = phys - op
    bar_kw = dict(width=0.62, edgecolor=SURFACE, linewidth=1.3, zorder=3)
    ax_b.bar(x, op, color=NAVY, **bar_kw)
    ax_b.bar(x, pending, bottom=op, color=PENDING, **bar_kw)
    b_top = max(phys.max(), p.trolleys_for_30) * 1.22
    ax_b.set_ylim(0, b_top)
    ax_b.yaxis.set_major_locator(MaxNLocator(4, integer=True))
    for k, v in enumerate(op):
        if v >= 0.16 * b_top:
            ax_b.text(k, v - 0.035 * b_top, str(v), ha="center", va="top", fontsize=7.5,
                      fontweight=600, color=SURFACE, zorder=5)
        else:  # short bar: sit the number right on top of the operational segment
            ax_b.text(k, v + 0.015 * b_top, str(v), ha="center", va="bottom", fontsize=7.5,
                      fontweight=600, color=INK, zorder=5)

    ax_b.axhline(p.trolleys_for_30, color=INK2, lw=1.0, ls=(0, (3, 3)), zorder=4)
    ax_b.annotate(f"{p.trolleys_for_30} needed\nfor {UPH_AT_TARGET} UPH",
                  xy=(1, p.trolleys_for_30), xycoords=("axes fraction", "data"), xytext=(8, 0),
                  textcoords="offset points", ha="left", va="center", fontsize=8.4, color=INK2,
                  linespacing=1.25, annotation_clip=False)

    for b in s["batches"]:
        k = b.arrival_idx - (WEEK_LABELS.index(weeks[0]))
        if 0 <= k < n:
            for ax in (ax_b, ax_c):
                ax.axvline(k, color=NAVY, lw=1.0, alpha=0.45, zorder=2)
            ax_b.text(k, phys[k] + 0.03 * b_top, f"+{b.qty}", ha="center", va="bottom", fontsize=8.2,
                      fontweight=700, color=INK, zorder=6,
                      bbox=dict(boxstyle="round,pad=0.2", fc=SURFACE, ec="none", alpha=0.9))

    handles_b = [
        Patch(facecolor=NAVY, label="Operational"),
        Patch(facecolor=PENDING, label="Pending adjustment"),
        Line2D([0], [0], color=INK2, lw=1.0, ls=(0, (3, 3)), label=f"Needed for {UPH_AT_TARGET} UPH"),
    ]
    _panel_header(ax_b, "Trolley fleet  ·  units", handles_b)

    # ================= Panel C: shipments =================
    start_idx = WEEK_LABELS.index(weeks[0])
    pt_per_week = (RIGHT - LEFT) * FIG_W * 72 / n
    row_h = 0.58

    def segment(y, x0, x1, color, labels):
        x0c, x1c = max(x0, -0.5), min(x1, n - 0.5)
        if x1c <= x0c:
            return
        ax_c.barh(y, x1c - x0c, left=x0c, height=row_h, color=color, edgecolor=SURFACE,
                  linewidth=1.4, zorder=3)
        width = (x1c - x0c) * pt_per_week
        for lab in labels:
            if text_pts(lab, 8) + 10 <= width:
                ax_c.text((x0c + x1c) / 2, y, lab, ha="center", va="center", fontsize=8,
                          fontweight=600, color=INK, zorder=4)
                break

    rows = {"Batch 1": 1, "Batch 2": 0}
    for b in s["batches"]:
        y = rows[b.name]
        k_ship = b.ship_idx - start_idx
        k_customs = k_ship + TRANSIT_WEEKS
        k_arr = b.arrival_idx - start_idx
        segment(y, k_ship, k_customs, TRANSIT_FILL, [f"Transit · {TRANSIT_WEEKS} wk", "Transit", "T"])
        segment(y, k_customs, k_arr, CUSTOMS_FILL, [f"Customs · {b.customs} wk", "Customs", "C"])
        if b.ready_idx is not None and b.ready_idx - start_idx <= n - 1:
            k_ready = b.ready_idx - start_idx
            segment(y, k_arr, k_ready, PENDING, ["Adjustment", "Adj."])
            ax_c.plot(k_ready, y, marker="D", ms=7.5, color=NAVY, mec=SURFACE, mew=1.5, zorder=5)
            ax_c.text(k_ready, y + row_h / 2 + 0.07, f"Ready {b.ready_label}", ha="center", va="bottom",
                      fontsize=7.8, fontweight=600, color=INK, zorder=6, clip_on=False)
        else:
            segment(y, k_arr, n - 0.5, PENDING,
                    [f"Adjustment · ready {b.ready_label} →", f"Ready {b.ready_label} →",
                     f"{b.ready_label} →"])

    ax_c.set_ylim(-0.6, 1.72)
    ax_c.set_yticks([1, 0])
    ax_c.set_yticklabels([f"{b.name}  +{b.qty}" for b in s["batches"]], fontsize=9, color=INK,
                         fontweight=500)
    ax_c.grid(False)
    handles_c = [
        Patch(facecolor=TRANSIT_FILL, label="Transit"),
        Patch(facecolor=CUSTOMS_FILL, label="Customs"),
        Patch(facecolor=PENDING, label="Adjustment"),
        Line2D([0], [0], color="none", marker="D", ms=6.5, mfc=NAVY, mec=SURFACE, label="Fully operational"),
    ]
    _panel_header(ax_c, "Shipments & adjustment", handles_c)
    _week_axis(ax_c, weeks, s["years"])

    return _to_png(fig)


def draw_scrap_chart(s: dict) -> bytes:
    weeks, n = s["weeks"], len(s["weeks"])
    start_idx = WEEK_LABELS.index(weeks[0])
    fig, ax = plt.subplots(figsize=(FIG_W, 3.9), facecolor=SURFACE)
    fig.subplots_adjust(left=LEFT, right=RIGHT, top=0.80, bottom=0.2)
    _style_axis(ax)
    _shade_shutdown((ax,), weeks)

    in_window = set(s["window_k"])
    xs = [k for k, v in enumerate(s["scrap_modules"]) if v is not None]
    vals = [s["scrap_modules"][k] for k in xs]
    colors = [VIOLET if k in in_window else OUT_OF_WINDOW for k in xs]
    ax.bar(xs, vals, width=0.62, color=colors, edgecolor=SURFACE, linewidth=1.3, zorder=3)

    top = max(vals) if vals and max(vals) > 0 else 1.0
    ax.set_ylim(0, top * 1.75)
    ax.yaxis.set_major_locator(MaxNLocator(4))
    for k, v in zip(xs, vals):
        if k in in_window and v > 0:
            ax.text(k, v + top * 0.04, f"{v:.1f}", ha="center", va="bottom", fontsize=7.8,
                    color=INK2, zorder=5)

    # Bracket + total over the accumulation window
    wk = sorted(in_window)
    if wk:
        y = top * 1.33
        x0, x1 = wk[0] - 0.36, wk[-1] + 0.36
        ax.plot([x0, x0, x1, x1], [y - top * 0.07, y, y, y - top * 0.07], color=INK2, lw=1.1,
                zorder=5, solid_capstyle="butt")
        total = round(s["window_total"])
        label = (f"≈ {total:,} module{'' if total == 1 else 's'} accumulated  ·  "
                 f"{week_range(s['window'])}")
        # Keep the label inside the plot when the window sits near either edge.
        half = text_pts(label, 10) / 2 / ((RIGHT - LEFT) * FIG_W * 72 / n)
        cx = min(max((x0 + x1) / 2, -0.5 + half), n - 0.5 - half)
        ax.text(cx, y + top * 0.06, label, ha="center", va="bottom", fontsize=10, fontweight=700,
                color=INK, zorder=6)

    # Context markers for the first batch
    fb = s["first_batch"]
    tr = blended_transform_factory(ax.transData, ax.transAxes)
    for idx, label in ((fb.arrival_idx, f"{fb.name} on site"), (fb.ready_idx, f"{fb.name} ready")):
        if idx is None:
            continue
        k = idx - start_idx
        if 0 <= k < n:
            ax.axvline(k, color=NAVY, lw=1.0, alpha=0.45, zorder=2)
            ax.text(k + 0.12, 0.97, label, transform=tr, ha="left", va="top", fontsize=7.8,
                    color=INK2, zorder=6)

    handles = [Patch(facecolor=VIOLET, label="In accumulation window"),
               Patch(facecolor=OUT_OF_WINDOW, label="Outside window")]
    _panel_header(ax, f"Scrap modules per week  ·  {s['p'].scrap_pct:g}% of production", handles)
    _week_axis(ax, weeks, s["years"])
    return _to_png(fig)


@st.cache_data(show_spinner=False, max_entries=64)
def render_charts(param_values: tuple, code_version: str) -> tuple:
    """Charts are cached on plain values so toggling back and forth is instant.

    code_version is part of the cache key only: a redeploy with new drawing code
    must never serve charts cached by the previous version.
    """
    s = build_scenario(Params(*param_values))
    main_png = draw_main_chart(s)
    scrap_png = draw_scrap_chart(s) if s["p"].scrap_on else None
    return main_png, scrap_png


# =============================================================================
# Page
# =============================================================================
st.set_page_config(page_title="Trolley Capacity Ramp-Up", page_icon="▣", layout="wide")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
.block-container{padding-top:2.4rem;padding-bottom:3rem;max-width:1480px}
[data-testid="stImage"] img{border-radius:14px;border:1px solid rgba(11,11,11,.08)}
.tcr{font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;color:#0b0b0b}
.tcr-req{background:#fff;border:1px solid rgba(11,11,11,.08);border-radius:16px;overflow:hidden;margin-bottom:6px}
.tcr-req svg{display:block;width:100%;height:auto}
.tcr-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:24px 0 20px}
.tcr-kpi{background:#fff;border:1px solid rgba(11,11,11,.08);border-radius:14px;padding:16px 18px 15px;box-shadow:0 1px 2px rgba(11,11,11,.04)}
.tcr-kpi-label{font-size:12.5px;font-weight:500;color:#52514e}
.tcr-kpi-value{font-size:30px;font-weight:650;letter-spacing:-.02em;line-height:1.1;margin-top:8px;color:#0b0b0b}
.tcr-kpi-unit{font-size:14px;font-weight:500;color:#52514e;letter-spacing:0;margin-left:5px}
.tcr-kpi-sub{font-size:12.5px;color:#898781;margin-top:7px;line-height:1.45}
.tcr-hero{font-size:52px;font-weight:700;letter-spacing:-.03em;line-height:1}
.tcr-section{font-size:21px;font-weight:650;letter-spacing:-.015em;margin:34px 0 4px}
.tcr-section-sub{font-size:14px;color:#52514e;margin-bottom:14px;line-height:1.5}
.tcr-note{font-size:12.5px;color:#898781;line-height:1.55;margin-top:6px}
.tcr-table-wrap{overflow-x:auto;border:1px solid rgba(11,11,11,.08);border-radius:12px;background:#fff}
table.tcr-table{border-collapse:collapse;font-size:12.5px;font-variant-numeric:tabular-nums;width:100%}
.tcr-table th,.tcr-table td{padding:7px 10px;text-align:right;white-space:nowrap;border-bottom:1px solid #efeee9;color:#0b0b0b}
.tcr-table th:first-child,.tcr-table td:first-child{text-align:left;position:sticky;left:0;background:#fff;font-weight:500;z-index:1}
.tcr-table thead th{color:#898781;font-weight:600;font-size:11.5px;background:#fafaf8}
.tcr-table thead th:first-child{background:#fafaf8}
.tcr-table .sd{background:#f4f3ef}
.tcr-table .short{color:#a12a2a;background:#fbeaea;font-weight:600}
.tcr-table .win{background:#eeecf8;font-weight:600}
.tcr-table tr:last-child td{border-bottom:none}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------- Sidebar
st.sidebar.markdown("### Scenario controls")

with st.sidebar.expander("Display", expanded=True):
    unit_mode = st.selectbox("Unit format", UNIT_OPTIONS)
    label_all = st.checkbox("Label every data point", value=False,
                            help="Off: only the key call-outs are labeled (cleaner for presenting).")

with st.sidebar.expander("Fleet & adjustment", expanded=True):
    base_fleet = st.number_input("Base fleet (trolleys today)", min_value=20, max_value=60, value=35, step=5)
    target_trolleys_for_30_uph = st.slider("Trolleys required for 30 UPH", min_value=60, max_value=200,
                                           value=90, step=5)
    adjustment_rate = st.slider("Mechanical adjustment rate (trolleys / week)", min_value=1, max_value=10,
                                value=2, step=1)

with st.sidebar.expander("Shutdown · CW52 & CW1", expanded=True):
    adjust_in_shutdown = st.toggle("Keep adjusting trolleys during shutdown", value=False,
                                   help="Off: no trolleys are adjusted in CW52 and CW1.")
    if adjust_in_shutdown:
        shutdown_rate = st.slider("Adjustment rate during shutdown (trolleys / week)", min_value=1,
                                  max_value=15, value=adjustment_rate, step=1)
    else:
        shutdown_rate = 0

with st.sidebar.expander("Shipments & customs", expanded=True):
    st.caption(f"Sea transit is fixed at {TRANSIT_WEEKS} weeks; customs adds 1–2 weeks.")
    st.markdown("**Batch 1**")
    batch1_qty = st.number_input("Batch 1 quantity", min_value=10, max_value=50, value=24, step=2)
    batch1_start_week = st.selectbox("Batch 1 shipment week", SHIP_WEEK_OPTIONS,
                                     index=SHIP_WEEK_OPTIONS.index("CW46"), key="b1_start")
    batch1_customs = st.slider("Batch 1 customs (weeks)", min_value=1, max_value=2, value=2, key="b1_customs")
    st.markdown("**Batch 2**")
    batch2_qty = st.number_input("Batch 2 quantity", min_value=10, max_value=60, value=30, step=2)
    batch2_start_week = st.selectbox("Batch 2 shipment week", SHIP_WEEK_OPTIONS,
                                     index=SHIP_WEEK_OPTIONS.index("CW1"), key="b2_start")
    batch2_customs = st.slider("Batch 2 customs (weeks)", min_value=1, max_value=2, value=2, key="b2_customs")

with st.sidebar.expander("Scrap", expanded=True):
    enable_scrap = st.toggle("Show scrap", value=False)
    scrap_pct = st.slider("Scrap percentage (%)", min_value=0.0, max_value=30.0, value=3.0, step=0.5,
                          disabled=not enable_scrap)
    scrap_mode = st.radio("Count accumulated scrap", SCRAP_MODES, disabled=not enable_scrap)
    data_weeks = list(DEMAND_UNITS_PER_WEEK)
    scrap_range = st.select_slider("CW range", options=data_weeks, value=(data_weeks[0], data_weeks[-1]),
                                   disabled=not (enable_scrap and scrap_mode == SCRAP_MODES[2]))

params = Params(
    unit_mode=unit_mode, label_all=label_all, base_fleet=int(base_fleet),
    trolleys_for_30=int(target_trolleys_for_30_uph), rate=int(adjustment_rate),
    adjust_in_shutdown=bool(adjust_in_shutdown), shutdown_rate=int(shutdown_rate),
    b1_qty=int(batch1_qty), b1_ship=batch1_start_week, b1_customs=int(batch1_customs),
    b2_qty=int(batch2_qty), b2_ship=batch2_start_week, b2_customs=int(batch2_customs),
    scrap_on=bool(enable_scrap), scrap_pct=float(scrap_pct), scrap_mode=scrap_mode,
    scrap_range=tuple(scrap_range),
)
s = build_scenario(params)
CODE_VERSION = hashlib.md5(Path(__file__).read_bytes()).hexdigest()
main_png, scrap_png = render_charts(astuple(params), CODE_VERSION)

unit = s["unit"]
dec, u = unit["decimals"], unit["short"]
weeks, years = s["weeks"], s["years"]


def kpi(label: str, value: str, unit_txt: str = "", sub: str = "") -> str:
    unit_html = f'<span class="tcr-kpi-unit">{unit_txt}</span>' if unit_txt else ""
    return (f'<div class="tcr-kpi"><div class="tcr-kpi-label">{label}</div>'
            f'<div class="tcr-kpi-value">{value}{unit_html}</div>'
            f'<div class="tcr-kpi-sub">{sub}</div></div>')


# ---------------------------------------------------------------- Trolley requirements (top)
def map_view_selector() -> str:
    """Compact three-way switch for the requirements map (simple -> all stations -> full layout)."""
    options = list(requirements_map.VIEWS)
    label_of = requirements_map.VIEWS.get
    if hasattr(st, "segmented_control"):
        choice = st.segmented_control("Map view", options, default=options[0], format_func=label_of,
                                      key="map_view", label_visibility="collapsed")
    else:  # older Streamlit
        choice = st.radio("Map view", options, format_func=label_of, horizontal=True, key="map_view",
                          label_visibility="collapsed")
    # Clicking the active segment deselects it; keep showing the last view instead of failing.
    if choice not in requirements_map.VIEWS:
        choice = st.session_state.get("map_view_last", options[0])
    st.session_state["map_view_last"] = choice
    return choice


map_slot = st.empty()  # the map renders above its own controls
c_view, c_dl, _ = st.columns([2.3, 1.5, 3.2])
with c_view:
    map_view = map_view_selector()
req_svg = requirements_map.build_svg(view=map_view)
map_slot.markdown(f'<div class="tcr-req">{req_svg}</div>', unsafe_allow_html=True)
with c_dl:
    st.download_button("Download map (SVG)", data=req_svg.encode("utf-8"),
                       file_name=f"trolley_requirements_{map_view}.svg", mime="image/svg+xml")
st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- Main chart
st.image(main_png)
c1, c2, _ = st.columns([1.1, 1.1, 5])

table = pd.DataFrame({
    "Week": weeks,
    "Year": years,
    "Trolleys on site": s["phys"],
    "Operational trolleys": s["op"],
    "Pending adjustment": s["phys"] - s["op"],
    f"Capacity ({u})": np.round(s["cap"], dec),
    f"Demand ({u})": [None if d is None else round(d, dec) for d in s["demand"]],
    f"Headroom ({u})": [round(s["headroom"][k], dec) if k in s["headroom"] else None for k in range(len(weeks))],
})
if params.scrap_on:
    table["Scrap (modules)"] = [None if v is None else round(v, 2) for v in s["scrap_modules"]]
    table["In scrap window"] = [k in set(s["window_k"]) for k in range(len(weeks))]

with c1:
    st.download_button("Download chart (PNG)", data=main_png, file_name="trolley_capacity_vs_demand.png",
                       mime="image/png")
with c2:
    st.download_button("Download data (CSV)", data=table.to_csv(index=False).encode("utf-8"),
                       file_name="trolley_capacity_weekly.csv", mime="text/csv")

st.markdown(
    '<div class="tcr tcr-note">Assumptions: capacity scales linearly with operational trolleys '
    f'({params.trolleys_for_30} trolleys = {UPH_AT_TARGET} UPH); {HOURS_PER_WEEK:.0f} production hours and '
    f'{DAYS_PER_WEEK:.0f} days per week; new trolleys are adjusted first-in-first-out starting the week they '
    f'arrive; shipment = {TRANSIT_WEEKS} weeks transit + customs.</div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- Weekly detail
with st.expander("Weekly detail", expanded=False):
    sd_cols = {k for k, w in enumerate(weeks) if w in SHUTDOWN_WEEKS}
    win_cols = set(s["window_k"]) if params.scrap_on else set()

    def cell(k: int, text: str, extra: str = "") -> str:
        cls = " ".join(c for c in (("sd" if k in sd_cols else ""), extra) if c)
        return f'<td class="{cls}">{text}</td>' if cls else f"<td>{text}</td>"

    head = "<th></th>" + "".join(
        f'<th class="sd">{w}</th>' if k in sd_cols else f"<th>{w}</th>" for k, w in enumerate(weeks))
    rows_html = [
        ("Trolleys on site", [cell(k, f"{v}") for k, v in enumerate(s["phys"])]),
        ("Operational", [cell(k, f"{v}") for k, v in enumerate(s["op"])]),
        ("Pending adjustment", [cell(k, f"{v}" if v else "–") for k, v in enumerate(s["phys"] - s["op"])]),
        (f"Capacity ({u})", [cell(k, fmt(v, dec)) for k, v in enumerate(s["cap"])]),
        (f"Demand ({u})", [cell(k, "–" if d is None else fmt(d, dec)) for k, d in enumerate(s["demand"])]),
        (f"Headroom ({u})", [
            cell(k, fmt_signed(s["headroom"][k], dec), "short" if s["headroom"][k] < 0 else "")
            if k in s["headroom"] else cell(k, "–") for k in range(len(weeks))]),
    ]
    if params.scrap_on:
        rows_html.append(("Scrap (modules)", [
            cell(k, "–" if v is None else f"{v:.1f}", "win" if k in win_cols else "")
            for k, v in enumerate(s["scrap_modules"])]))
    body = "".join(f"<tr><td>{name}</td>{''.join(cells)}</tr>" for name, cells in rows_html)
    st.markdown(f'<div class="tcr tcr-table-wrap"><table class="tcr-table"><thead><tr>{head}</tr></thead>'
                f"<tbody>{body}</tbody></table></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- Scrap accumulation
if params.scrap_on:
    n_weeks_window = len(s["window"])
    avg = s["window_total"] / n_weeks_window if n_weeks_window else 0.0
    capped_note = (f" Demand data ends at {WEEK_LABELS[LAST_DATA_IDX]}, so the count stops there."
                   if s["window_capped"] else "")
    st.markdown(
        '<div class="tcr"><div class="tcr-section">Scrap accumulation</div>'
        f'<div class="tcr-section-sub">How many scrap modules pile up {s["window_why"]}, at '
        f'{params.scrap_pct:g}% of production.{capped_note}</div></div>',
        unsafe_allow_html=True,
    )
    hero = (f'<div class="tcr-kpi"><div class="tcr-kpi-label">Scrap modules accumulated</div>'
            f'<div class="tcr-hero" style="margin-top:10px">≈ {round(s["window_total"]):,}</div>'
            f'<div class="tcr-kpi-sub">Expected value {s["window_total"]:,.1f} modules</div></div>')
    window_card = kpi("Accumulation window", week_range(s["window"]), "",
                      f"{n_weeks_window} week{'s' if n_weeks_window != 1 else ''} · {s['window_why']}")
    rate_card = kpi("Average build-up", f"{avg:,.1f}", "modules / week",
                    f"{params.scrap_pct:g}% of {s['window_produced']:,} modules produced in the window")
    st.markdown(f'<div class="tcr tcr-kpis" style="margin-top:6px">{hero}{window_card}{rate_card}</div>',
                unsafe_allow_html=True)
    if n_weeks_window:
        st.image(scrap_png)
    else:
        st.info("The first batch arrives before production starts, so no scrap accumulates in this window.")

# ---------------------------------------------------------------- Benchmark
st.markdown(
    '<div class="tcr"><div class="tcr-section">Benchmark · trolley fleets across plants</div>'
    '<div class="tcr-section-sub">Number of outfeed and infeed trolleys per plant against line output (UPH).'
    '</div></div>',
    unsafe_allow_html=True,
)
st.image(str(APP_DIR / "table.jpg"))
