"""Dark signal card. render_chart() returns a PNG BytesIO for send_photo."""
from __future__ import annotations

import io
from datetime import datetime
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

from config import BRAND, PAYOUT_DISPLAY

KAMPALA = ZoneInfo("Africa/Kampala")

BG = "#0c1118"
PANEL = "#141b26"
GRID = "#1e2836"
TEXT = "#e8eef6"
MUTED = "#8b9bb0"
GREEN = "#1fbf75"
RED = "#f0434d"
GOLD = "#e2b657"
LINE = "#5b8def"


def _pretty(display_pair):
    raw = display_pair.replace("-OTC", "")
    if raw.startswith("USD") and "/" not in raw and len(raw) > 3:
        return "USD/" + raw[3:] + "-OTC"
    return display_pair


def render_chart(sig, test=False):
    candles = sig.candles.tail(48)
    fig = plt.figure(figsize=(10.8, 7.2), dpi=140, facecolor=BG)
    ax = fig.add_axes([0.07, 0.22, 0.88, 0.58])
    ax.set_facecolor(PANEL)

    width = 0.62
    xs = list(range(len(candles)))
    for i, (_, row) in enumerate(candles.iterrows()):
        o, h, l, c = float(row.Open), float(row.High), float(row.Low), float(row.Close)
        up = c >= o
        color = GREEN if up else RED
        ax.plot([i, i], [l, h], color=color, linewidth=1.1, solid_capstyle="round")
        body_low = min(o, c)
        body_h = max(abs(c - o), (h - l) * 0.015 or 1e-8)
        ax.add_patch(Rectangle((i - width / 2, body_low), width, body_h, facecolor=color, edgecolor=color, linewidth=0))

    ax.axhline(sig.support, color=GREEN, linestyle="--", linewidth=0.8, alpha=0.7)
    ax.axhline(sig.resistance, color=RED, linestyle="--", linewidth=0.8, alpha=0.7)
    ax.axhline(sig.entry_price, color=GOLD, linestyle=":", linewidth=1.0, alpha=0.9)

    ax.grid(True, color=GRID, linewidth=0.6)
    ax.tick_params(colors=MUTED, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.set_xlim(-1, max(len(xs) - 1, 1) + 1)
    ax.set_xticks([])
    last = float(candles["Close"].iloc[-1])
    ax.text(
        len(xs) - 1,
        last,
        f"  {last:.5f}",
        color=GOLD,
        fontsize=8,
        va="center",
    )

    arrow = "CALL  ↑" if sig.direction == "CALL" else "PUT  ↓"
    tone = GREEN if sig.direction == "CALL" else RED
    name = _pretty(sig.display_pair)
    title = f"{BRAND}   ·   {'TEST CARD' if test else 'M1 SIGNAL'}"
    fig.text(0.07, 0.90, title, color=GOLD, fontsize=11, fontweight="bold")
    fig.text(0.07, 0.845, name, color=TEXT, fontsize=20, fontweight="bold")
    fig.text(0.62, 0.845, arrow, color=tone, fontsize=20, fontweight="bold")

    meta = (
        f"Trend {sig.trend}    ·    Confidence {sig.confidence}%    ·    "
        f"Entry {sig.entry_time} EAT    ·    Payout {PAYOUT_DISPLAY}"
    )
    fig.text(0.07, 0.795, meta, color=MUTED, fontsize=9)

    fig.text(0.07, 0.09, f"Support  {sig.support:.5f}", color=GREEN, fontsize=9)
    fig.text(0.37, 0.09, f"Price  {sig.entry_price:.5f}", color=GOLD, fontsize=9)
    fig.text(0.64, 0.09, f"Resistance  {sig.resistance:.5f}", color=RED, fontsize=9)
    stamp = datetime.now(KAMPALA).strftime("%d %b %Y  %H:%M EAT")
    fig.text(0.07, 0.04, stamp + "    ·    not financial advice", color=MUTED, fontsize=8)

    fig.patches.append(
        FancyBboxPatch(
            (0.015, 0.015),
            0.97,
            0.97,
            boxstyle="round,pad=0.005,rounding_size=0.012",
            transform=fig.transFigure,
            fill=False,
            edgecolor=LINE,
            linewidth=1.2,
        )
    )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    buf.name = "signal.png"
    return buf
