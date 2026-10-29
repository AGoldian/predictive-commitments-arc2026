#!/usr/bin/env python3
# SPDX-License-Identifier: MIT-0
"""Render retained aggregate counts only; never import or rerun a DEV reader.

From the workspace root:
    .venv/bin/python paper/figures/writeup-visuals-20261029/coverage-build.py
Requires matplotlib. Input and output paths are relative to this script.
"""
from pathlib import Path
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "coverage-data.json").read_text())

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 14,
    "axes.unicode_minus": False,
    "svg.fonttype": "none",
    "svg.hashsalt": "arc-prize-dev-coverage-v1",
    "pdf.fonttype": 42,
    "axes.edgecolor": "#6E7784",
    "text.color": "#202A36",
    "axes.labelcolor": "#465361",
    "xtick.color": "#465361",
    "ytick.color": "#202A36",
})

fig = plt.figure(figsize=(10, 7.2), facecolor="white")
ax = fig.add_axes((0.11, 0.29, 0.64, 0.49))
ax.set_facecolor("white")
fig.text(0.055, 0.94, "Prediction-packet coverage on DEV", fontsize=23,
         fontweight="bold", va="top")
fig.text(0.055, 0.875, "Four exposed public games · seed 101", fontsize=15,
         color="#536170", va="top")

for row, y in zip(DATA["rows"], (2, 1, 0)):
    percent = row["coverage_rate"] * 100
    ax.barh(y, percent, height=0.46, color="#2F6F9F", zorder=3)
    ax.text(1.045, y,
            f"{percent:.1f}%\n{row['valid_predictions']} / {row['eligible_actions']}",
            transform=ax.get_yaxis_transform(), va="center", ha="left",
            fontsize=16, linespacing=1.3)

ax.set_yticks((2, 1, 0), ("B1", "A1", "P"), fontsize=18, fontweight="bold")
ax.tick_params(axis="y", length=0, pad=13)
ax.set_ylim(-0.62, 2.65)
ax.set_xlim(0, 100)
ax.set_xticks((0, 25, 50, 75, 100))
ax.xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
ax.tick_params(axis="x", labelsize=14, length=4, pad=8)
ax.xaxis.grid(True, color="#E5EAF0", linewidth=0.9)
ax.set_axisbelow(True)
ax.axvline(DATA["feasibility_gate"]["coverage_rate"] * 100,
           color="#303D4B", linestyle=(0, (5, 4)), linewidth=1.5, zorder=4)
ax.text(50, 2.54, "Frozen feasibility gate: 50%", fontsize=13.5,
        ha="center", va="bottom", color="#303D4B", zorder=5,
        bbox={"facecolor": "white", "edgecolor": "none", "pad": 2})
ax.text(1.045, 2.54, "V / D", transform=ax.get_yaxis_transform(),
        fontsize=13.5, color="#536170", ha="left", va="bottom")
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_linewidth(0.9)
ax.set_xlabel("Eligible executed actions with a valid packet", fontsize=14,
              labelpad=13)

fig.text(0.055, 0.145, "B0 excluded by design. Coverage is not accuracy, score or efficacy.",
         fontsize=13.2, va="top", color="#465361")
fig.text(0.055, 0.10, "Actions are not IID; no CI, significance or causal advantage is shown.",
         fontsize=13.2, va="top", color="#465361")
fig.text(0.055, 0.055, "Sources: retained DEV evidence · claims O23, O25, O26", fontsize=12.5,
         va="top", color="#657181")

description = DATA["caption"]
for name, dpi in (("coverage-dev.png", 140), ("coverage-dev-700.png", 70)):
    fig.savefig(HERE / name, dpi=dpi, facecolor="white", metadata={
        "Title": "Prediction-packet coverage on DEV",
        "Description": description,
        "Author": "Alexander Serov",
    })
fig.savefig(HERE / "coverage-dev.svg", facecolor="white", metadata={
    "Title": "Prediction-packet coverage on DEV", "Description": description,
    "Date": None,
})
fig.savefig(HERE / "coverage-dev.pdf", facecolor="white", metadata={
    "Title": "Prediction-packet coverage on DEV", "Subject": description,
    "Author": "Alexander Serov", "CreationDate": None, "ModDate": None,
})
plt.close(fig)

sources = [f"- `{row['arm']}`: `{row['source']['path']}`\n"
           f"  SHA256 `{row['source']['sha256']}`" for row in DATA["rows"]]
(HERE / "coverage-caption.md").write_text(
    "# DEV prediction-packet coverage\n\n" + description + "\n\n"
    + "Source aggregates (no reader replay or new scoring):\n\n"
    + "\n".join(sources) + "\n\n"
    + "The complete source pins, frozen gate, scope and qualifications are in "
    "`coverage-data.json`. Rebuild with `coverage-build.py`.\n"
)
print("Rendered coverage-dev.png, coverage-dev-700.png, SVG, PDF and caption.")
