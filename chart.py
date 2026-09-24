from __future__ import annotations
from io import BytesIO
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from analyzer import Signal

def render_chart(signal: Signal) -> BytesIO:
    df = signal.candles.copy()
    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=120)
    fig.patch.set_facecolor("#0b0f14")
    ax.set_facecolor("#0b0f14")
    opens = df["Open"].tolist()
    highs = df["High"].tolist()
    lows = df["Low"].tolist()
    closes = df["Close"].tolist()
    for i, (o, h, l, c) in enumerate(zip(opens, highs, lows, closes)):
        color = "#26c281" if c >= o else "#e74c3c"
        ax.vlines(i, l, h, color=color, linewidth=0.9, zorder=2)
        body_low = min(o, c)
        body_h = max(abs(c - o), (max(highs) - min(lows)) * 0.002)
        ax.add_patch(Rectangle((i - 0.32, body_low), 0.64, body_h, facecolor=color, edgecolor=color, linewidth=0.4, zorder=3))
    n = len(df)
    zone_start = max(0, n - 25)
    ax.axvspan(zone_start, n - 1, color="#d4af37", alpha=0.08, zorder=1)
    ax.plot(range(zone_start, n), [signal.support] * (n - zone_start), color="#f1c40f", linestyle="--", linewidth=1.0)
    ax.plot(range(zone_start, n), [signal.resistance] * (n - zone_start), color="#f1c40f", linestyle="--", linewidth=1.0)
    ax.set_xlim(-1, n)
    ax.tick_params(colors="#8b9bb4", labelsize=7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#243041")
    ax.spines["bottom"].set_color("#243041")
    ax.grid(True, color="#1b2430", linewidth=0.6)
    ax.set_xticks([])
    ax.set_title(f"{signal.display_pair}  |  M1  |  {signal.direction}", color="#e8eef7", fontsize=10, pad=10, loc="left")
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    buf.name = "signal.png"
    return buf
