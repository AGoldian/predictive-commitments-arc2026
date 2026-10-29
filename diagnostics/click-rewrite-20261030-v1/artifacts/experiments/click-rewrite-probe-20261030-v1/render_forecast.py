# SPDX-License-Identifier: MIT-0
"""Illustrate the saved partial forecast and actual public return, without inference."""
from pathlib import Path
import json
from PIL import Image, ImageColor, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
RUN = ROOT / 'run'


def font(size):
    for name in ('/System/Library/Fonts/Supplemental/Arial.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


palette = [ImageColor.getrgb(c) for c in [
    '#000000', '#0074D9', '#FF4136', '#2ECC40', '#FFDC00', '#AAAAAA',
    '#F012BE', '#FF851B', '#7FDBFF', '#870C25', '#B8A2E0', '#FFCF80',
    '#617C8C', '#7CBA91', '#A46042', '#FFFFFF']]
before = json.loads((RUN / 'observation-06.json').read_text())['frame'][-1]
after = json.loads((RUN / 'observation-07.json').read_text())['frame'][-1]
packet = json.loads((RUN / 'commitment.json').read_text())
forecasts = {p['candidate_id']: p['prediction']['forecast'] for p in packet['forecasts']}
assert forecasts['affine-d4-5'] == forecasts['toggle']
cells = forecasts['toggle']
assert len(cells) == 48 and all(after[v['row']][v['col']] == v['value'] for v in cells)
forecast = Image.new('RGB', (64, 64))
for r in range(64):
    for c in range(64):
        forecast.putpixel((c, r), ImageColor.getrgb('#e0e3e9' if (r // 4 + c // 4) % 2 else '#edf0f5'))
for cell in cells:
    forecast.putpixel((cell['col'], cell['row']), palette[cell['value']])
panels = []
for grid in (before, after):
    image = Image.new('RGB', (64, 64))
    image.putdata([palette[v] for row in grid for v in row])
    panels.append(image)
canvas = Image.new('RGB', (1120, 535), '#f6f7fa')
draw = ImageDraw.Draw(canvas)
draw.text((30, 18), 'One new click: 48 changed cells predicted', font=font(30), fill='#182133')
draw.text((30, 58), 'Six hypotheses committed before the trial. Two made the same correct partial forecast.', font=font(18), fill='#45516b')
for index, (image, label, caption) in enumerate([
    (panels[0], 'Before the probe', 'Automatically selected click: (46,18)'),
    (forecast, 'Saved prediction', '48 known cells; 4,048 UNKNOWN'),
    (panels[1], 'Actual new public return', '48/48 known correct; 49 cells changed')]):
    x, y = 30 + index * 365, 123
    draw.text((x, 92), label, font=font(22), fill='#182133')
    canvas.paste(image.resize((320, 320), Image.Resampling.NEAREST), (x, y))
    draw.text((x, 449), caption, font=font(16), fill='#33415b')
draw.text((30, 485), 'Selected public DEV scene, seed303. One changed cell omitted; zero levels completed.', font=font(18), fill='#45516b')
canvas.save(ROOT / 'partial-forecast-evidence.png')
