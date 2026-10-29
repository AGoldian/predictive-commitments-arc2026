#!/usr/bin/env python3
# SPDX-License-Identifier: MIT-0
"""Build an owned method PNG/SVG and schematic GIF; no experimental data is used."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont, __version__ as pillow_version

ROOT = Path(__file__).resolve().parents[3]
SIZE = (1920, 1280)
GIF_SIZE = (1080, 700)
SCALE = 2
INK = "#17253b"
MUTED = "#53667d"
LINE = "#d6e0eb"
COLORS = ("#087f8c", "#2e68b1", "#527a39", "#a66a14", "#6d4bc3")
PALE = ("#edf8f8", "#eef4fc", "#f1f7ec", "#fff7e9", "#f4effc")
REGULAR = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
BOLD = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")


class Drawing:
    def __init__(self, regular: Path, bold: Path, size=SIZE):
        self.size = size
        self.image = Image.new("RGB", (size[0] * SCALE, size[1] * SCALE), "white")
        self.draw = ImageDraw.Draw(self.image)
        self.regular, self.bold = regular, bold
        self.svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{size[0]}" height="{size[1]}" viewBox="0 0 {size[0]} {size[1]}">',
            '<title>Predictive commitments and the four allocation controls</title>',
            '<desc>Schematic method illustration. An immutable optional prediction precedes dispatch; '
            'public outcomes resolve scored pairs before a later shared allocation ticket. '
            'The four controls are B0, B1, A1 and P. No game rollout or measured values are shown.</desc>',
            f'<rect width="{size[0]}" height="{size[1]}" fill="white"/>',
        ]

    def rect(self, box, fill="white", stroke=None, width=1, radius=16):
        x, y, r, b = box
        self.draw.rounded_rectangle(tuple(v * SCALE for v in box), radius * SCALE,
                                    fill=fill, outline=stroke, width=width * SCALE)
        border = "" if stroke is None else f' stroke="{stroke}" stroke-width="{width}"'
        self.svg.append(f'<rect x="{x}" y="{y}" width="{r-x}" height="{b-y}" rx="{radius}" fill="{fill}"{border}/>')

    def line(self, points, color=LINE, width=2):
        self.draw.line([(x*SCALE, y*SCALE) for x, y in points], fill=color,
                       width=width*SCALE, joint="curve")
        pts = " ".join(f"{x},{y}" for x, y in points)
        self.svg.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round"/>')

    def arrow(self, points, color=LINE, width=3, size=9):
        self.line(points, color, width)
        (ax, ay), (bx, by) = points[-2:]
        if bx != ax:
            sign = 1 if bx > ax else -1
            tri = [(bx, by), (bx-sign*size, by-size*.65), (bx-sign*size, by+size*.65)]
        else:
            sign = 1 if by > ay else -1
            tri = [(bx, by), (bx-size*.65, by-sign*size), (bx+size*.65, by-sign*size)]
        self.draw.polygon([(round(x*SCALE), round(y*SCALE)) for x, y in tri], fill=color)
        pts = " ".join(f"{x},{y}" for x, y in tri)
        self.svg.append(f'<polygon points="{pts}" fill="{color}"/>')

    def text(self, x, y, content, size=24, color=INK, bold=False, max_width=None):
        font = ImageFont.truetype(str(self.bold if bold else self.regular), size*SCALE)
        if max_width is not None and self.draw.textlength(content, font=font) > max_width*SCALE:
            raise ValueError(f"Text exceeds its drawing box: {content}")
        self.draw.text((x*SCALE, y*SCALE), content, font=font, fill=color, anchor="lt")
        self.svg.append(f'<text x="{x}" y="{y}" dominant-baseline="text-before-edge" '
                        f'font-family="Arial, sans-serif" font-size="{size}" '
                        f'font-weight="{700 if bold else 400}" fill="{color}">{escape(content)}</text>')

    def png(self):
        return self.image.resize(self.size, Image.Resampling.LANCZOS)


def render(regular: Path, bold: Path, focus: int = 0):
    d = Drawing(regular, bold)
    d.text(90, 55, "A prediction is fixed before the action", 51, bold=True, max_width=1740)
    d.text(90, 124, "Public outcomes are resolved before a later shared-compute decision.", 28,
           MUTED, max_width=1740)
    banners = (
        "METHOD OVERVIEW  •  Instrumented path: B1 / A1 / P; learned multiplier: A1 / P only",
        "1 / 5  COMMIT  •  A prediction or abstention is bound before execution",
        "2 / 5  DISPATCH  •  Execute the exact action through the permitted public interface",
        "3 / 5  OBSERVE  •  Read the returned public frame and permitted metadata",
        "4 / 5  RESOLVE  •  Pair the original commitment once with its observable outcome",
        "5 / 5  ALLOCATE  •  Freeze the learned multiplier for a new admission ticket",
        "CONTROLS  •  P versus A1 isolates the added representation under fixed L2",
    )
    d.rect((90, 177, 1830, 216), "#f1f5fa", radius=9)
    d.text(108, 186, banners[focus], 22, MUTED, bold=True, max_width=1705)
    titles = ("Commit", "Dispatch", "Observe", "Resolve", "Next ticket")
    lines = (
        (("optional q_t or abstain", 24), ("frame change / level / failure", 21),
         ("bound to action + payload", 22)),
        (("one action a_t", 25), ("permitted SDK only", 23),
         ("no future observations", 22)),
        (("public return o_(t+1)", 24), ("last returned frame", 23),
         ("+ permitted metadata", 22)),
        (("observable outcome y", 24), ("valid pair: (p − y)²", 24),
         ("unavailable ≠ correct", 22)),
        (("settled history → r̂", 24), ("A1/P: baseline × (0.5 + r̂)", 21),
         ("freeze multiplier per ticket", 21)),
    )
    feet = ("Fixed before dispatch", "Exact action receipt", "No hidden state",
            "No retrospective revision", "Capacity: 2 exchanges")
    for i in range(5):
        x = 90 + i*355
        active = focus in (0, i+1)
        d.rect((x, 238, x+320, 488), PALE[i], COLORS[i] if active else LINE,
               4 if focus == i+1 else 2)
        d.rect((x+20, 261, x+57, 298), COLORS[i], radius=10)
        d.text(x+31, 270, str(i+1), 20, "white", bold=True)
        d.text(x+72, 264, titles[i], 30, bold=True, max_width=227)
        for row, (label, size) in enumerate(lines[i]):
            d.text(x+22, 327+row*36, label, size, max_width=278)
        d.line([(x+22, 440), (x+298, 440)], LINE, 1)
        d.text(x+22, 457, feet[i], 20, MUTED, max_width=279)
        if i < 4:
            color = COLORS[i+1] if focus in (0, i+2) else "#aebdce"
            d.arrow([(x+327, 365), (x+349, 365)], color, 3, 8)
    d.arrow([(250, 489), (250, 521), (1315, 521), (1315, 491)], "#8a9caf", 2, 8)
    d.rect((530, 503, 1160, 539), "white", radius=4)
    d.text(548, 511, "Original commitment + exact action return", 23, MUTED, max_width=600)

    d.rect((90, 561, 1830, 672), "#f6f8fb", LINE, 1, 14)
    d.text(115, 582, "Settled history", 26, bold=True)
    d.text(115, 623, "last 8 eligible actions", 23, MUTED)
    d.line([(421, 579), (421, 654)], LINE, 2)
    d.text(447, 581, "A1 / P common inputs", 25, bold=True)
    d.text(447, 620, "progress + coverage + mean(p), mean(p²), mean(y)", 23, MUTED,
           max_width=745)
    d.line([(1231, 579), (1231, 654)], LINE, 2)
    d.text(1259, 581, "P adds event Brier means", 25, COLORS[4], bold=True, max_width=541)
    d.text(1259, 620, "mean((p − y)²) on the same scored pairs", 23, MUTED, max_width=541)
    d.text(91, 692, "Error sample: valid, observable pairs only. RESET / undo / known refusals excluded; missing labels stay unavailable.",
           22, MUTED, max_width=1740)

    d.text(90, 744, "Four arms, different questions", 31, bold=True)
    arms = (
        ("B0", "#53667d", "#f4f6f8", ("No prediction interface", "Baseline prompts + batches"),
         "Baseline priority", "Practical baseline"),
        ("B1", COLORS[0], PALE[0], ("Optional predictions", "Shared instrumentation"),
         "Baseline priority", "Instrumentation control"),
        ("A1", COLORS[1], PALE[1], ("Same optional predictions", "Common progress + paired moments"),
         "Learned multiplier", "Matched allocation control"),
        ("P", COLORS[4], PALE[4], ("Same optional predictions", "Same common inputs + Brier means"),
         "Learned multiplier", "Primary representation test"),
    )
    for i, (arm, color, pale, body, rule, role) in enumerate(arms):
        x = 90 + i*441
        d.rect((x, 797, x+417, 1055), pale, color if focus == 6 and i >= 2 else LINE,
               4 if focus == 6 and i >= 2 else 2)
        d.text(x+24, 819, arm, 35, color, bold=True)
        d.text(x+24, 874, body[0], 24, max_width=369)
        d.text(x+24, 912, body[1], 22, max_width=369)
        d.line([(x+24, 955), (x+393, 955)], LINE, 1)
        d.text(x+24, 975, rule, 25, color, bold=True, max_width=369)
        d.text(x+24, 1015, role, 21, MUTED, max_width=369)
    d.text(90, 1080, "Primary contrast: P − A1 tests the added pairing-sensitive representation under fixed L2.",
           25, COLORS[4], bold=True, max_width=1740)
    d.text(90, 1130, "Two different targets", 25, bold=True)
    d.text(90, 1167, "q_t: NEXT-action events.  r̂: current-level completion within 8,192 target tokens or 20 nonautomatic actions.",
           24, MUTED, max_width=1740)
    d.text(90, 1203, "P falls back to A1 when all event residuals are missing. Only completed public history enters a new ticket.",
           23, MUTED, max_width=1740)
    d.text(90, 1251, "SCHEMATIC METHOD ILLUSTRATION  •  NO ROLLOUT, MEASURED PROBABILITIES OR PERFORMANCE RESULT",
           18, MUTED, bold=True, max_width=1740)
    d.svg.append("</svg>")
    return d


def render_compact(regular: Path, bold: Path, focus: int = 0):
    """Compact animation for a roughly 700px-wide inline Markdown image."""
    d = Drawing(regular, bold, GIF_SIZE)
    d.text(50, 34, "Commit before dispatch. Allocate after outcomes.", 36,
           bold=True, max_width=980)
    labels = (
        "B1 / A1 / P path  •  A1 / P learned ticket shown",
        "1 / 5  COMMIT  •  Forecast or abstain BEFORE execution",
        "2 / 5  DISPATCH  •  Execute the exact action",
        "3 / 5  OBSERVE  •  Use only the public return",
        "4 / 5  RESOLVE  •  Score the original valid pair once",
        "5 / 5  NEXT TICKET  •  Freeze the learned multiplier",
    )
    d.rect((50, 94, 1030, 136), "#f1f5fa", radius=9)
    d.text(66, 105, labels[focus], 24, MUTED, bold=True, max_width=948)
    boxes = ((50, 164, 350, 342), (390, 164, 690, 342),
             (730, 164, 1030, 342), (140, 420, 520, 598), (560, 420, 940, 598))
    titles = ("Commit", "Dispatch", "Observe", "Resolve", "Next ticket")
    body = (("q_t or abstain", "fixed before dispatch"),
            ("execute action a_t", "permitted public SDK"),
            ("returned public frame", "and permitted metadata"),
            ("original p + observable y", "valid error: (p − y)²"),
            ("settled history → frozen r̂", "A1/P: base × (0.5 + r̂)"))
    for i, box in enumerate(boxes):
        x, y, r, b = box
        d.rect(box, PALE[i], COLORS[i] if focus in (0, i+1) else LINE,
               4 if focus == i+1 else 2)
        d.rect((x+18, y+21, x+56, y+59), COLORS[i], radius=10)
        d.text(x+29, y+29, str(i+1), 22, "white", bold=True)
        d.text(x+70, y+25, titles[i], 30, bold=True, max_width=r-x-89)
        d.text(x+20, y+89, body[i][0], 22, max_width=r-x-40)
        d.text(x+20, y+128, body[i][1], 22, max_width=r-x-40)
    paths = (((356, 253), (383, 253)), ((696, 253), (723, 253)),
             ((880, 348), (880, 377), (330, 377), (330, 412)),
             ((527, 509), (553, 509)))
    for i, points in enumerate(paths):
        d.arrow(points, COLORS[i+1] if focus in (0, i+2) else "#aebdce", 3, 9)
    d.text(50, 628, "q_t forecasts next-action events; r̂ predicts level progress.", 24,
           MUTED, max_width=980)
    d.text(50, 670, "SCHEMATIC ONLY  •  No rollout, measured probabilities or performance.", 22,
           MUTED, bold=True, max_width=980)
    d.svg.append("</svg>")
    return d


def build(output: Path, regular: Path, bold: Path):
    output.mkdir(parents=True, exist_ok=True)
    products = [output/"method-loop.png", output/"method-loop.svg",
                output/"method-loop.gif", output/"method-manifest.json"]
    if any(p.exists() for p in products):
        raise ValueError("Output files already exist; choose a fresh --output directory.")
    for p in (regular, bold):
        if not p.is_file():
            raise ValueError(f"Missing render font: {p}")
    static = render(regular, bold)
    static.png().save(output/"method-loop.png", optimize=True)
    (output/"method-loop.svg").write_text("\n".join(static.svg)+"\n")
    frames = [render_compact(regular, bold, n).png() for n in range(6)]
    palette = frames[0].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    indexed = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in frames]
    durations = [2000, 2000, 1800, 1800, 2200, 2400]
    indexed[0].save(output/"method-loop.gif", save_all=True,
                    append_images=indexed[1:], duration=durations, loop=0,
                    disposal=2, optimize=False)
    with Image.open(output/"method-loop.gif") as animation:
        for i in range(animation.n_frames):
            animation.seek(i)
            decoded = animation.convert("RGB")
            decoded.save(output/f"method-frame-{i:02}.png", optimize=True)
            if i in (1, 4, 5):
                decoded.resize((700, 454), Image.Resampling.LANCZOS).save(
                    output/f"method-inline-{i:02}.png", optimize=True)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    inputs = [ROOT/"paper/paper.tex", ROOT/"paper/kaggle-writeup.txt",
              ROOT/"paper/figures/method-controls-v1/method-controls.svg"]
    manifest = {
        "kind": "Owned schematic method illustration; no empirical data",
        "schema_version": 1,
        "graphic_license": "CC-BY-4.0",
        "builder_license": "MIT-0",
        "static_width": SIZE[0], "static_height": SIZE[1],
        "animation_width": GIF_SIZE[0], "animation_height": GIF_SIZE[1],
        "animation_frames": 6, "frame_duration_ms": durations,
        "animation_minimum_font_px": 22,
        "inline_preview_width_px": 700,
        "loop": "infinite",
        "render_library": {"name": "Pillow", "version": pillow_version},
        "font_sha256": {p.name: sha(p) for p in (regular, bold)},
        "font_files_redistributed": False,
        "builder_sha256": sha(Path(__file__)),
        "method_sources_sha256": {str(p.relative_to(ROOT)): sha(p) for p in inputs},
        "measured_values_depicted": False,
        "game_data_or_rollout_depicted": False,
        "caption_static": "An immutable optional prediction precedes action dispatch. Public outcomes resolve scored pairs before a later shared-allocation ticket. B0/B1/A1/P isolate different questions; P versus A1 tests the added representation under fixed L2.",
        "caption_animation": "Compact schematic of commit, dispatch, observe, resolve and the next A1/P ticket. Highlighted stages indicate logical order only, not a measured rollout, probabilities, timing or allocator benefit. The full four-arm comparison is in the static figure.",
        "alt_text": "Five boxes: commit, dispatch, observe, resolve, next ticket. A history strip separates common moments from P-only Brier means. Four arm cards distinguish B0, B1, A1 and P; a note separates next-action forecasts from fitted level-completion probability.",
        "limits": "Illustrates only the implemented event-only mechanism. Does not depict experimental success, hidden game state, visual-mask adoption, equal actual cost or a causal effect of extra computation.",
        "files_sha256": {p.name: sha(p) for p in sorted(output.glob("method-*"))
                         if p.is_file() and p.name != "method-manifest.json"},
    }
    (output/"method-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False,
                                                      sort_keys=True, indent=2)+"\n")
    return {"output": str(output), "png": sha(output/"method-loop.png"),
            "gif": sha(output/"method-loop.gif")}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=Path(__file__).resolve().parent,
                   help="Fresh output directory; defaults to this script's directory")
    p.add_argument("--font-regular", type=Path, default=REGULAR)
    p.add_argument("--font-bold", type=Path, default=BOLD)
    args = p.parse_args()
    print(json.dumps(build(args.output, args.font_regular, args.font_bold)))
