"""Trolley capacity ramp-up - scenario planner.

Streamlit app that compares the capacity of the outfeed/infeed trolley fleet
against production demand week by week, including incoming trolley shipments,
mechanical adjustment of new trolleys, the year-end shutdown and scrap build-up.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import astuple, dataclass, replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib import patheffects as path_effects  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402
from matplotlib.transforms import blended_transform_factory, offset_copy  # noqa: E402

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

# Plan shown at the previous review: baseline for "What changed".
# Batch 1 shipped CW46 (on site CW52) and adjustment paused during the shutdown.
PREVIOUS_PLAN = {"b1_qty": 30, "b1_ship": "CW46", "b1_customs": 2, "rate": 5,
                 "adjust_in_shutdown": False, "shutdown_rate": 0}
OP_TARGET = 50  # "50+ trolleys operational" milestone

# Values before the actions (from the action list). The "after" side of every action is
# read from the sidebar, so the panel always matches the scenario on screen.
ACTION_BASELINE = {"b1_ship": "CW46", "b1_qty": 24, "rate": 2}

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
# Combined chart: lines sit on top of navy bars, so they use warm/green hues with a white halo.
CAP_LINE, CAP_LINE_TEXT = "#eb6834", "#a8461d"
DEM_LINE, DEM_LINE_TEXT = "#1baf7a", "#0f7a52"
PENDING_SOFT = "#b7d3f6"
CAP_SHARE_OF_BAR = 0.45 # combined chart: capacity line height as a share of the navy bar

FIG_W = 14.0
LEFT, RIGHT = 0.1, 0.905

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
    chart_layout: str = "combined"
    chart_height: int = 100  # main chart height, % of the default proportion


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


def _draw_shipments(ax_c, s: dict, compact: bool = False) -> None:
    """Gantt of both batches: transit, customs, adjustment and the week each is fully operational."""
    weeks, n = s["weeks"], len(s["weeks"])
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
    if compact:
        ax_c.set_ylabel("Shipments", fontsize=9.5, color=INK2, labelpad=10)
        ax_c.legend(handles=handles_c, ncol=len(handles_c), loc="upper right", bbox_to_anchor=(1.0, 0.0),
                    bbox_transform=offset_copy(ax_c.transAxes, fig=ax_c.figure, y=-21, units="points"),
                    frameon=False, fontsize=8.6, handlelength=1.6, handleheight=0.9, columnspacing=1.4,
                    handletextpad=0.5, labelcolor=INK2, borderaxespad=0)
    else:
        _panel_header(ax_c, "Shipments & adjustment", handles_c)
    _week_axis(ax_c, weeks, s["years"])

    for b in s["batches"]:
        k = b.arrival_idx - start_idx
        if 0 <= k < n:
            ax_c.axvline(k, color=NAVY, lw=1.0, alpha=0.45, zorder=2)


def _draw_split(s: dict) -> bytes:
    """Three stacked panels: capacity vs demand, fleet, shipments."""
    p, unit = s["p"], s["unit"]
    dec, u = unit["decimals"], unit["short"]
    weeks, n = s["weeks"], len(s["weeks"])
    x = np.arange(n)
    cap, op, phys = s["cap"], s["op"], s["phys"]

    fig = plt.figure(figsize=(FIG_W, 9.2 * p.chart_height / 100), facecolor=SURFACE)
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
    b_top = phys.max() * 1.22
    ax_b.set_ylim(0, b_top)
    ax_b.yaxis.set_major_locator(MaxNLocator(4, integer=True))
    for k, v in enumerate(op):
        if v >= 0.16 * b_top:
            ax_b.text(k, v - 0.035 * b_top, str(v), ha="center", va="top", fontsize=7.5,
                      fontweight=600, color=SURFACE, zorder=5)
        else:  # short bar: sit the number right on top of the operational segment
            ax_b.text(k, v + 0.015 * b_top, str(v), ha="center", va="bottom", fontsize=7.5,
                      fontweight=600, color=INK, zorder=5)


    for b in s["batches"]:
        k = b.arrival_idx - (WEEK_LABELS.index(weeks[0]))
        if 0 <= k < n:
            ax_b.axvline(k, color=NAVY, lw=1.0, alpha=0.45, zorder=2)
            ax_b.text(k, phys[k] + 0.03 * b_top, f"+{b.qty}", ha="center", va="bottom", fontsize=8.2,
                      fontweight=700, color=INK, zorder=6,
                      bbox=dict(boxstyle="round,pad=0.2", fc=SURFACE, ec="none", alpha=0.9))

    handles_b = [
        Patch(facecolor=NAVY, label="Operational"),
        Patch(facecolor=PENDING, label="Pending adjustment"),
    ]
    _panel_header(ax_b, "Trolley fleet  ·  units", handles_b)

    _draw_shipments(ax_c, s)
    return _to_png(fig)


def auto_y_max(phys) -> float:
    """Automatic trolley-axis maximum: just enough headroom for the "+N" label on the tallest bar."""
    return float(phys.max()) * 1.075


def _place_corner_block(fig, ax, ax2, leg, ttl, phys, arrival_ks) -> None:
    """Align the title + legend block's top with the tallest bar; lift it only if it would touch
    the bars underneath it."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    px = fig.dpi / 72.0
    lb, tb = leg.get_window_extent(renderer), ttl.get_window_extent(renderer)
    right_x = ax.transData.inverted().transform((max(lb.x1, tb.x1), 0))[0]
    covered = [k for k in range(len(phys)) if k - 0.31 < right_x]  # bars are 0.62 wide
    bar_top_px = max(ax.transData.transform((k, phys[k]))[1] + (16 * px if k in arrival_ks else 0)
                     for k in covered)
    gap, title_gap = 10 * px, 8 * px
    block_h = lb.height + title_gap + tb.height
    ceiling = ax2.transAxes.transform((0, 0.99))[1]
    tallest_px = ax.transData.transform((0, float(phys.max())))[1]
    bottom = min(max(tallest_px - block_h, bar_top_px + gap), ceiling - block_h)
    to_axes = ax2.transAxes.inverted()
    leg.set_bbox_to_anchor((0.0, to_axes.transform((0, bottom))[1]), transform=ax2.transAxes)
    ttl.set_position((0.008, to_axes.transform((0, bottom + lb.height + title_gap))[1]))


def _draw_combined(s: dict) -> bytes:
    """Fleet bars and capacity / demand / scrap lines on one panel (as in the previous review),
    with the shipments Gantt underneath."""
    p, unit = s["p"], s["unit"]
    dec, u = unit["decimals"], unit["short"]
    sdec = 1 if dec else 0
    weeks, n = s["weeks"], len(s["weeks"])
    x = np.arange(n)
    cap, op, phys = s["cap"], s["op"], s["phys"]
    pending = phys - op

    main_in, gantt_in, gap_in, top_in, bottom_in = 5.6 * p.chart_height / 100, 1.3, 0.21, 0.12, 0.67
    fig_h = main_in + gantt_in + gap_in + top_in + bottom_in
    fig = plt.figure(figsize=(FIG_W, fig_h), facecolor=SURFACE)
    gs = fig.add_gridspec(2, 1, height_ratios=[main_in, gantt_in], hspace=gap_in / ((main_in + gantt_in) / 2),
                          left=LEFT, right=RIGHT, top=1 - top_in / fig_h, bottom=bottom_in / fig_h)
    ax = fig.add_subplot(gs[0])
    ax_c = fig.add_subplot(gs[1], sharex=ax)
    for a in (ax, ax_c):
        _style_axis(a)
    ax.tick_params(labelbottom=False)  # weeks are read on the shipments axis right below
    ax2 = ax.twinx()
    for side in ("top", "right", "left", "bottom"):
        ax2.spines[side].set_visible(False)
    ax2.tick_params(axis="y", colors=MUTED, labelsize=8.5, length=0, pad=6)

    sd_note = f"adjusting {p.shutdown_rate}/wk" if p.adjust_in_shutdown else "adjustment paused"
    _shade_shutdown((ax_c,), weeks)
    ref_k = s["ref_k"]

    # ---------------- bars: trolleys (left axis) ----------------
    bar_kw = dict(width=0.62, edgecolor=SURFACE, linewidth=1.3, zorder=2)
    ax.bar(x, op, color=NAVY, **bar_kw)
    ax.bar(x, pending, bottom=op, color=PENDING_SOFT, **bar_kw)
    l_top = auto_y_max(phys)
    ax.set_ylabel("Available trolleys", fontsize=9.5, color=INK2, labelpad=8)
    bar_label_y = {}  # week -> (y anchor in trolleys, "top"/"bottom") of the bar's value label
    for k, v in enumerate(op):
        if v >= 0.13 * l_top:
            ax.text(k, v - 0.022 * l_top, str(v), ha="center", va="top", fontsize=7.8,
                    fontweight=600, color=SURFACE, zorder=3)
            bar_label_y[k] = (v - 0.022 * l_top, "top")
        else:
            ax.text(k, v + 0.012 * l_top, str(v), ha="center", va="bottom", fontsize=7.8,
                    fontweight=600, color=INK, zorder=3)
            bar_label_y[k] = (v + 0.012 * l_top, "bottom")
    arrival_ks = set()
    for b in s["batches"]:
        k = b.arrival_idx - WEEK_LABELS.index(weeks[0])
        if 0 <= k < n:
            arrival_ks.add(k)
            ax.text(k, phys[k] + 0.014 * l_top, f"+{b.qty}", ha="center", va="bottom", fontsize=8.4,
                    fontweight=700, color=INK, zorder=3)
    sd_ks = [k for k, w in enumerate(weeks) if w in SHUTDOWN_WEEKS]
    if sd_ks:
        top_k = max(sd_ks, key=lambda k: phys[k])
        lift = 19 if any(k in arrival_ks for k in sd_ks) else 6  # clear the "+N" label
        cx = (min(sd_ks) + max(sd_ks)) / 2
        ax.annotate(sd_note, (cx, phys[top_k]), xytext=(0, lift), textcoords="offset points", ha="center",
                    va="bottom", fontsize=7.8, color=MUTED, zorder=6)
        ax.annotate("Shutdown", (cx, phys[top_k]), xytext=(0, lift + 12), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8.6, fontweight=600, color=INK2, zorder=6)

    # ---------------- lines: capacity, demand, scrap (right axis) ----------------
    mask = np.array([d is not None for d in s["demand"]])
    xd = x[mask]
    dem = np.array([d for d in s["demand"] if d is not None], dtype=float)
    scrap = np.array([d for d in s["scrap_conv"] if d is not None], dtype=float)
    # Capacity is proportional to operational trolleys, so the right axis is scaled to put the
    # capacity line at a fixed share of each navy bar: it always runs inside the bars, clear of
    # the bar labels, and the two scales stay in a meaningful relation.
    cap_per_trolley = UPH_AT_TARGET * unit["cap_factor"] / p.trolleys_for_30
    r_top = cap_per_trolley * l_top / CAP_SHARE_OF_BAR
    if dem.size:
        r_top = max(r_top, dem.max() * 1.15)
    bottom_pad = 0.075 if p.label_all else 0.0  # room under zero for the lowest labels
    ax.set_ylim(-bottom_pad * l_top, l_top)
    ax2.set_ylim(-bottom_pad * r_top, r_top)
    sd_cols = [k for k, w in enumerate(weeks) if w in SHUTDOWN_WEEKS]
    if sd_cols:  # shade stops at the height of the tallest bar, like the title block
        ax.axvspan(min(sd_cols) - 0.5, max(sd_cols) + 0.5, ymin=0,
                   ymax=(phys.max() + bottom_pad * l_top) / (l_top * (1 + bottom_pad)),
                   color=SHUTDOWN_FILL, zorder=0, lw=0)
    ax.set_yticks([t for t in MaxNLocator(5, integer=True).tick_values(0, l_top) if 0 <= t <= l_top])
    if bottom_pad:
        ax.spines["bottom"].set_visible(False)
        ax.axhline(0, color=BASELINE, linewidth=0.9, zorder=2)
    ax2.set_yticks([t for t in MaxNLocator(5).tick_values(0, r_top) if 0 <= t <= r_top])
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}" if v >= 10 or v == 0 else f"{v:g}"))
    ax2.set_ylabel(f"Capacity, demand & scrap ({u})", fontsize=9.5, color=INK2, rotation=270, labelpad=16)

    has_short = bool(s["short_weeks"])
    if has_short:
        ax2.fill_between(xd, cap[mask], dem, where=dem > cap[mask], interpolate=True,
                         color=CRITICAL, alpha=0.22, lw=0, zorder=1)
    halo = [path_effects.Stroke(linewidth=4.8, foreground=SURFACE), path_effects.Normal()]

    def series_line(xs, ys, color, marker, ms, z, **kw):
        ax2.plot(xs, ys, color=color, linewidth=kw.pop("lw", 2.2), solid_capstyle="round",
                 solid_joinstyle="round", path_effects=halo, zorder=z, **kw)
        ax2.plot(xs, ys, linestyle="none", marker=marker, markersize=ms, markerfacecolor=color,
                 markeredgecolor=SURFACE, markeredgewidth=1.3, zorder=z + 0.5)

    series_line(x, cap, CAP_LINE, "o", 5.8, 4)
    series_line(xd, dem, DEM_LINE, "s", 5.2, 5)
    if p.scrap_on:
        series_line(xd, scrap, VIOLET, "^", 5.6, 5, lw=1.8, linestyle=(0, (4, 2)), dash_capstyle="butt")

    px = fig.dpi / 72.0
    chip = dict(boxstyle="round,pad=0.18", fc=SURFACE, ec="none", alpha=0.92)

    def y_px(xv, yv):
        return ax2.transData.transform((xv, yv))[1]

    # End labels: capacity sits above its last point (the right edge holds the axis);
    # demand / scrap end at the last week with data and are labeled to the right, kept apart.
    if not p.label_all:
        ax2.annotate(f"Capacity {fmt(cap[-1], dec)}", (n - 1, cap[-1]), xytext=(4, 9),
                     textcoords="offset points", ha="right", va="bottom", fontsize=9, fontweight=600,
                     color=INK, zorder=8, bbox=chip)
    ends = []
    if xd.size:
        ends.append((xd[-1], dem[-1], f"Demand {fmt(dem[-1], dec)}"))
        if p.scrap_on:
            ends.append((xd[-1], scrap[-1], f"Scrap {fmt(scrap[-1], sdec)}"))
    floor = None
    for xv, yv, text in sorted(ends, key=lambda e: e[1]):
        natural = y_px(xv, yv)
        target = natural if floor is None else max(natural, floor + 14 * px)
        floor = target
        ax2.annotate(text, (xv, yv), xytext=(9, (target - natural) / px), textcoords="offset points",
                     ha="left", va="center", fontsize=9, fontweight=600, color=INK, zorder=8, bbox=chip)

    if p.label_all:
        series = [(list(cap), lambda v: fmt(v, dec), CAP_LINE_TEXT, set()),
                  (s["demand"], lambda v: fmt(v, dec), DEM_LINE_TEXT, {ref_k})]
        if p.scrap_on:
            series.append((s["scrap_conv"], lambda v: fmt(v, sdec), VIOLET, {ref_k}))
        room = (7.4 + 5) * px + 3
        text_h = 7.4 * 1.3 * px

        def bar_label_span(k):
            y, anchor = bar_label_y[k]
            y0 = ax.transData.transform((k, y))[1]
            return (y0 - text_h, y0) if anchor == "top" else (y0, y0 + text_h)

        def label_span(ypix, side):
            off = 5 * px
            return ((ypix + off, ypix + off + text_h) if side == "up" else
                    (ypix - off - text_h, ypix - off) if side == "down" else
                    (ypix - text_h / 2, ypix + text_h / 2))

        def clashes(span, other):
            return span[0] < other[1] + 1 and other[0] < span[1] + 1
        placements = {"up": dict(xytext=(0, 5), ha="center", va="bottom"),
                      "down": dict(xytext=(0, -5), ha="center", va="top"),
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
                if side != "right" and clashes(label_span(ypix, side), bar_label_span(k)):
                    side = "right"  # keep the bar's own number readable
                ax2.annotate(text, (k, v), textcoords="offset points", fontsize=7.4, fontweight=600,
                             color=color, zorder=7,
                             bbox=dict(boxstyle="round,pad=0.14", fc=SURFACE, ec="none", alpha=0.9),
                             **placements[side])

    # ---------------- header: title + a legend row per axis ----------------
    bar_handles = [
        Patch(facecolor=NAVY, label="Operational trolleys"),
        Patch(facecolor=PENDING_SOFT, label="Pending adjustment"),
    ]
    line_handles = [
        Line2D([0], [0], color=CAP_LINE, lw=2.2, marker="o", ms=5.5, mfc=CAP_LINE, mec=SURFACE,
               label=f"Capacity ({u})"),
        Line2D([0], [0], color=DEM_LINE, lw=2.2, marker="s", ms=5, mfc=DEM_LINE, mec=SURFACE,
               label=f"Production demand ({u})"),
    ]
    if p.scrap_on:
        line_handles.append(Line2D([0], [0], color=VIOLET, lw=1.8, ls=(0, (4, 2)), marker="^", ms=5.5,
                                   mfc=VIOLET, mec=SURFACE, label=f"Scrap ({p.scrap_pct:g}%)"))
    if has_short:
        line_handles.append(Patch(facecolor=CRITICAL, alpha=0.22, label="Shortfall"))
    # Title and legend sit inside the plot, right on top of the early (short) bars, so the chart
    # has no empty band: its ceiling is the tallest bar.
    leg = ax2.legend(handles=bar_handles + line_handles, ncol=1, loc="lower left", bbox_to_anchor=(0.0, 0.5),
                     frameon=False, fontsize=8.8, handlelength=1.9, handleheight=0.9, labelspacing=0.55,
                     handletextpad=0.6, labelcolor=INK2, borderaxespad=0.3)
    ttl = ax2.text(0.008, 0.5, "Trolley availability & capacity\nvs. production demand", transform=ax2.transAxes,
                   fontsize=11.5, fontweight=600, color=INK, ha="left", va="bottom", linespacing=1.25, zorder=9)
    _place_corner_block(fig, ax, ax2, leg, ttl, phys, arrival_ks)

    _draw_shipments(ax_c, s, compact=True)
    fig.align_ylabels([ax, ax_c])
    return _to_png(fig)


def draw_main_chart(s: dict) -> bytes:
    return _draw_split(s) if s["p"].chart_layout == "split" else _draw_combined(s)


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
.tcr-actions{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:28px;padding:6px 2px 4px}
.tcr-col-head{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#898781;margin-bottom:6px}
.tcr-act{display:flex;align-items:flex-start;gap:12px;padding:12px 0;border-bottom:1px solid #efeee9}
.tcr-act:last-child{border-bottom:none}
.tcr-act-ic{flex:none;width:24px;height:24px;border-radius:50%;background:#e8f4e8;color:#006300;display:inline-flex;align-items:center;justify-content:center;margin-top:1px}
.tcr-act-body{flex:1;min-width:0}
.tcr-act-title{font-size:14.5px;font-weight:600;color:#0b0b0b;line-height:1.35}
.tcr-act-sub{font-size:13px;color:#52514e;line-height:1.45;margin-top:2px}
.tcr-act-chg{flex:none;display:inline-flex;align-items:center;gap:7px;font-size:13px;padding:5px 11px;border-radius:999px;background:#f4f3ef;white-space:nowrap;margin-top:1px}
.tcr-act-chg .old,.tcr-imp-vals .old{color:#898781;text-decoration:line-through;text-decoration-color:rgba(137,135,129,.6)}
.tcr-act-chg .arr,.tcr-imp-vals .arr{color:#a9a79f}
.tcr-act-chg .new{color:#0b0b0b;font-weight:650}
.tcr-imp-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:10px}
.tcr-imp{background:#fff;border:1px solid rgba(11,11,11,.08);border-radius:14px;padding:14px 16px}
.tcr-imp-label{font-size:12.5px;font-weight:500;color:#52514e}
.tcr-imp-vals{display:flex;align-items:baseline;gap:9px;margin:8px 0 9px}
.tcr-imp-vals .old{font-size:15px}
.tcr-imp-vals .new{font-size:26px;font-weight:650;letter-spacing:-.02em;color:#0b0b0b}
.tcr-delta{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;padding:3px 9px;border-radius:999px}
.tcr-delta.good{color:#006300;background:#e8f4e8}
.tcr-delta.bad{color:#a12a2a;background:#fbeaea}
.tcr-delta.flat{color:#52514e;background:#f0efea}
.tcr-imp-sub{font-size:12px;color:#52514e;line-height:1.45;margin-top:9px}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------- Sidebar
st.sidebar.markdown("### Scenario controls")

with st.sidebar.expander("Display", expanded=True):
    unit_mode = st.selectbox("Unit format", UNIT_OPTIONS)
    chart_height = st.select_slider("Chart height", options=list(range(60, 161, 5)), value=100,
                                    format_func=lambda v: f"{v}%",
                                    help="Vertical proportion of the main chart (100% = default).")
    chart_layout = st.radio("Chart layout", ["Combined", "Split"], horizontal=True,
                            help="Combined: trolleys and capacity on one chart, as in the last review. "
                                 "Split: separate panels.")
    label_all = st.checkbox("Label every data point", value=False,
                            help="Off: only the key call-outs are labeled (cleaner for presenting).")

with st.sidebar.expander("Fleet & adjustment", expanded=True):
    base_fleet = st.number_input("Base fleet (trolleys today)", min_value=20, max_value=60, value=36, step=1)
    target_trolleys_for_30_uph = st.slider("Trolleys required for 30 UPH", min_value=60, max_value=200,
                                           value=90, step=5)
    adjustment_rate = st.slider("Mechanical adjustment rate (trolleys / week)", min_value=1, max_value=10,
                                value=5, step=1)

with st.sidebar.expander("Shutdown · CW52 & CW1", expanded=True):
    adjust_in_shutdown = st.toggle("Keep adjusting trolleys during shutdown", value=True,
                                   help="Off: no trolleys are adjusted in CW52 and CW1.")
    if adjust_in_shutdown:
        shutdown_rate = st.slider("Adjustment rate during shutdown (trolleys / week)", min_value=1,
                                  max_value=15, value=adjustment_rate, step=1)
    else:
        shutdown_rate = 0

with st.sidebar.expander("Shipments & customs", expanded=True):
    st.caption(f"Sea transit is fixed at {TRANSIT_WEEKS} weeks; customs adds 1–2 weeks.")
    st.markdown("**Batch 1**")
    batch1_qty = st.number_input("Batch 1 quantity", min_value=10, max_value=50, value=30, step=2)
    batch1_start_week = st.selectbox("Batch 1 shipment week", SHIP_WEEK_OPTIONS,
                                     index=SHIP_WEEK_OPTIONS.index(ACTION_BASELINE["b1_ship"]), key="b1_start")
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
    scrap_range=tuple(scrap_range), chart_layout=chart_layout.lower(),
    chart_height=int(chart_height),
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

# ---------------------------------------------------------------- Actions since last review
def expander(label: str, icon: str | None = None, expanded: bool = False):
    try:
        return st.expander(label, expanded=expanded, icon=icon)
    except TypeError:  # older Streamlit without expander icons
        return st.expander(label, expanded=expanded)


def week_shift(before_idx, after_idx) -> tuple[str, str]:
    """Delta text and tone for a milestone week (earlier is better)."""
    if before_idx is None or after_idx is None:
        return ("Within horizon" if after_idx is not None else "Beyond horizon",
                "good" if after_idx is not None else "bad")
    d = before_idx - after_idx
    if d == 0:
        return "No change", "flat"
    n = abs(d)
    return f"{n} week{'s' if n != 1 else ''} {'earlier' if d > 0 else 'later'}", "good" if d > 0 else "bad"


def count_shift(before: float, after: float, unit_txt: str, decimals: int = 0) -> tuple[str, str]:
    d = after - before
    if round(d, decimals) == 0:
        return "No change", "flat"
    return f"{fmt_signed(d, decimals)} {unit_txt}", "good" if d > 0 else "bad"


def impact_tile(label: str, before: str, after: str, delta: tuple[str, str], note: str = "") -> str:
    text, tone = delta
    icon = {"good": "▲", "bad": "▼", "flat": "–"}[tone]
    note_html = f'<div class="tcr-imp-sub">{note}</div>' if note else ""
    return (f'<div class="tcr-imp"><div class="tcr-imp-label">{label}</div>'
            f'<div class="tcr-imp-vals"><span class="old">{before}</span><span class="arr">→</span>'
            f'<span class="new">{after}</span></div>'
            f'<span class="tcr-delta {tone}">{icon} {text}</span>{note_html}</div>')


CHECK_SVG = ('<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M3.5 8.4l2.9 2.9 '
             '6.1-6.6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
             'stroke-linejoin="round"/></svg>')

prev = build_scenario(replace(params, **PREVIOUS_PLAN))
b1_now, b1_prev = s["batches"][0], prev["batches"][0]


def label_of(idx) -> str:
    return WEEK_LABELS[idx] if idx is not None else "beyond CW13"


def first_week(scn: dict, test):
    """Calendar index of the first visible week whose operational count passes test(count, start_count)."""
    start_idx = WEEK_LABELS.index(scn["weeks"][0])
    for k, v in enumerate(scn["op"]):
        if test(int(v), int(scn["op"][0])):
            return start_idx + k
    return None


def op_in(scn: dict, idx) -> int:
    return int(scn["op"][idx - WEEK_LABELS.index(scn["weeks"][0])])


ramp_prev, ramp_now = (first_week(x, lambda v, v0: v > v0) for x in (prev, s))
target_prev, target_now = (first_week(x, lambda v, v0: v >= OP_TARGET) for x in (prev, s))
ramp_note = (f"Batch 1 on site in {b1_now.arrival_label}"
             + ("; adjustment continues through the shutdown" if params.adjust_in_shutdown else ""))
tiles = [
    impact_tile("Adjustment ramp-up starts", label_of(ramp_prev), label_of(ramp_now),
                week_shift(ramp_prev, ramp_now), ramp_note),
    impact_tile(f"{OP_TARGET}+ trolleys operational", label_of(target_prev), label_of(target_now),
                week_shift(target_prev, target_now),
                f"{op_in(s, target_now)} operational trolleys in {label_of(target_now)}" if target_now else ""),
    impact_tile("Batch 1 fully operational", b1_prev.ready_label, b1_now.ready_label,
                week_shift(b1_prev.ready_idx, b1_now.ready_idx),
                f"{op_in(s, b1_now.ready_idx)} operational trolleys in {b1_now.ready_label}"
                if b1_now.ready_idx is not None and b1_now.ready_idx <= WEEK_LABELS.index(weeks[-1]) else ""),
    impact_tile("Trolley & secondary-function KPIs", "Not measured", "Measured", ("Enabled by the app", "good"),
                "Trolley use on the line and at Scrap center, Rework and Q-HUB, now measured and controlled "
                "with certainty"),
]
def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def build_actions(p: Params) -> list:
    """Action rows (title, detail, (before, after) or None); quantified ones follow the sidebar."""
    base = ACTION_BASELINE
    shift = WEEK_LABELS.index(base["b1_ship"]) - WEEK_LABELS.index(p.b1_ship)
    ship = (("Batch 1 shipment pulled ahead", f"Ships {plural(shift, 'week')} earlier") if shift > 0 else
            ("Batch 1 shipment moved", f"Ships {plural(-shift, 'week')} later") if shift < 0 else
            None)  # unchanged since the last review: not an action, so not listed
    dq = p.b1_qty - base["b1_qty"]
    qty = (("Batch 1 quantity increased", "More trolleys in the first shipment") if dq > 0 else
           ("Batch 1 quantity reduced", "Fewer trolleys in the first shipment") if dq < 0 else
           ("Batch 1 quantity confirmed", "Same number of trolleys in the first shipment"))
    dr = p.rate - base["rate"]
    rate = (("Adjustment rate increased", "More trolleys adjusted on site every week") if dr > 0 else
            ("Adjustment rate reduced", "Fewer trolleys adjusted on site every week") if dr < 0 else
            ("Adjustment rate confirmed", "Same number of trolleys adjusted on site every week"))
    rows = [(*ship, (base["b1_ship"], p.b1_ship))] if ship else []
    return rows + [
        (*qty, (str(base["b1_qty"]), f"{p.b1_qty} trolleys")),
        ("Supplier pre-adjusts trolleys", "Aligned with the supplier so trolleys arrive pre-adjusted, "
                                          "reducing the adjustment workload on site", None),
        (*rate, (str(base["rate"]), f"{p.rate} / week")),
        ("Trolley usage controls via app", "Control measures for trolley use created and implemented "
                                           "through the app", None),
    ]


def change_chip(chg) -> str:
    if not chg:
        return ""
    before, after = chg
    if before == after.split()[0]:  # unchanged: show the value only
        return f'<div class="tcr-act-chg"><span class="new">{after}</span></div>'
    return (f'<div class="tcr-act-chg"><span class="old">{before}</span><span class="arr">→</span>'
            f'<span class="new">{after}</span></div>')


actions_html = "".join(
    f'<div class="tcr-act"><span class="tcr-act-ic">{CHECK_SVG}</span>'
    f'<div class="tcr-act-body"><div class="tcr-act-title">{title}</div><div class="tcr-act-sub">{detail}</div></div>'
    f'{change_chip(chg)}</div>'
    for title, detail, chg in build_actions(params))

st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
with expander("Actions since the last review", icon=":material/fact_check:"):
    st.markdown(
        '<div class="tcr tcr-actions">'
        f'<div><div class="tcr-col-head">What we did</div>{actions_html}</div>'
        '<div><div class="tcr-col-head">What changed</div>'
        f'<div class="tcr-imp-grid">{"".join(tiles)}</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

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
