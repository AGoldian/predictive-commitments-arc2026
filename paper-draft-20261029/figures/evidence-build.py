#!/usr/bin/env python3
# SPDX-License-Identifier: MIT-0
"""Render only the whitelisted retained facts in evidence-data.json.

Run from the workspace root with .venv/bin/python and this script's path.
No experiment, API, reader, scorer or model is imported or executed.
"""
from pathlib import Path
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle


HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "evidence-data.json").read_text())
plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none",
                     "svg.hashsalt": "arc-prize-evidence-status-v1", "text.color": "#202C3A"})

fig = plt.figure(figsize=(10, 6.0), facecolor="#F7F9FC")
ax = fig.add_axes((0, 0, 1, 1))
ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis("off")
ax.text(.035, .942, "Coverage, efficacy, and official result", fontsize=23,
        fontweight="bold", va="top")
ax.text(.035, .873, "P method · three distinct evidence levels", fontsize=14.5,
        color="#586678", va="top")

Y, H, W = .25, .54, .294
X = (.035, .353, .671)
for x in X:
    ax.add_patch(FancyBboxPatch((x, Y), W, H,
        boxstyle="round,pad=0.008,rounding_size=0.016", facecolor="white",
        edgecolor="#DDE4ED", linewidth=1.1))

def badge(x, text, face, ink):
    ax.add_patch(FancyBboxPatch((x+.017, Y+.029), W-.034, .054,
        boxstyle="round,pad=0.003,rounding_size=0.007", facecolor=face,
        edgecolor="none"))
    ax.text(x+W/2, Y+.056, text, ha="center", va="center", fontsize=10.8,
            fontweight="bold", color=ink)

# Distinct geometric icons convey status without a brand or color-only key.
x = X[0]
ax.add_patch(Polygon(((x+.018,.729),(x+.037,.776),(x+.056,.729)),
                     closed=True, facecolor="#FFF2D8", edgecolor="#A56A14", linewidth=1.2))
ax.text(x+.037,.744,"!",ha="center",va="center",fontsize=13,fontweight="bold",color="#89570E")
ax.text(x+.071,.752,"DEV P",va="center",fontsize=16,fontweight="bold")
ax.text(x+.019,.657,f"{DATA['dev_p']['rate']*100:.1f}%",fontsize=33,fontweight="bold",va="center")
ax.text(x+.021,.569,"89 valid / 417 eligible",fontsize=13.2,va="center",color="#48586A")
ax.text(x+.021,.523,"prediction packets / actions",fontsize=11.5,va="center",color="#657386")
bar_x, bar_y, bar_w = x+.021,.435,W-.042
ax.add_patch(Rectangle((bar_x,bar_y),bar_w,.014,facecolor="#E7ECF2",edgecolor="none"))
ax.add_patch(Rectangle((bar_x,bar_y),bar_w*DATA['dev_p']['rate'],.014,facecolor="#B87B23",edgecolor="none"))
gate_x=bar_x+bar_w*DATA['dev_p']['frozen_gate']
ax.plot((gate_x,gate_x),(.425,.463),color="#526174",linewidth=1.1)
ax.text(x+.021,.389,"Frozen feasibility gate: 50%",fontsize=11.7,color="#536377")
badge(x,"FEASIBILITY FAILED","#FFF2D8","#89570E")

x = X[1]
for cx in (x+.024,x+.052):
    ax.add_patch(Circle((cx,.751),.008,facecolor="white",edgecolor="#627187",linewidth=1.3))
ax.plot((x+.032,x+.044),(.751,.751),linestyle=(0,(2,2)),color="#627187",linewidth=1.2)
ax.text(x+.071,.752,"P − A1 contrast",va="center",fontsize=15.6,fontweight="bold")
ax.text(x+.019,.657,"Unavailable",fontsize=23.7,fontweight="bold",va="center")
ax.text(x+.021,.543,"Main study stopped\nafter B1 evidence\nrefusal.",fontsize=14.0,
        linespacing=1.45,va="center",color="#48586A")
badge(x,"NO EFFICACY RESULT","#EDF1F6","#536377")

x = X[2]
ax.add_patch(Circle((x+.038,.751),.020,facecolor="#EAF2FA",edgecolor="#366E9D",linewidth=1.2))
ax.add_patch(Rectangle((x+.030,.741),.016,.020,facecolor="#366E9D",edgecolor="none"))
ax.text(x+.071,.752,"Official P",va="center",fontsize=16,fontweight="bold")
ax.text(x+.019,.657,DATA['official_p']['public_score'],fontsize=33,fontweight="bold",va="center")
ax.text(x+.021,.552,"Submission 57749129\nCOMPLETE",fontsize=13.2,
        linespacing=1.45,va="center",color="#48586A")
ax.text(x+.021,.409,"Rerun cause, runtime\nand traces unobserved.",fontsize=12.2,
        linespacing=1.4,va="center",color="#657386")
badge(x,"OFFICIAL PUBLIC SCORE","#EAF2FA","#366E9D")

ax.text(.035,.170,"DEV: four exposed public games · seed 101",fontsize=13.5,color="#48586A",va="top")
ax.text(.035,.118,"Official score is distinct from DEV prediction coverage.",fontsize=13.5,color="#48586A",va="top")
ax.text(.035,.064,"These observations establish neither full reproduction nor an advantage.",
        fontsize=12.5,color="#657386",va="top")

description=DATA["caption"]
for name,dpi in (("evidence-status.png",140),("evidence-status-700.png",70)):
    fig.savefig(HERE/name,dpi=dpi,facecolor=fig.get_facecolor(),metadata={
        "Title":"Coverage, efficacy, and official result","Description":description,
        "Author":"Alexander Serov"})
fig.savefig(HERE/"evidence-status.svg",facecolor=fig.get_facecolor(),metadata={
    "Title":"Coverage, efficacy, and official result","Description":description,"Date":None})
plt.close(fig)
(HERE/"evidence-caption.md").write_text("# Evidence status\n\n"+description+"\n\n"
    +"Exact retained artifact paths and SHA256 pins are in `evidence-data.json`. "
    +"Rebuild with `evidence-build.py`; no current RUNNING status is embedded.\n")
print("Rendered evidence-status PNG, 700px PNG, SVG and caption.")
