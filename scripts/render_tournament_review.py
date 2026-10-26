"""Low-memory, one-worker MP4 from the static saved-pose review contract."""
import argparse
import bisect
import ctypes
import json
import math
import os
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


class Memory(ctypes.Structure):
    _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(k, ctypes.c_ulonglong) for k in ['total_physical', 'available_physical', 'total_page', 'available_page', 'total_virtual', 'available_virtual', 'extended']]


def reserve():
    if os.name != 'nt':
        return None
    status = Memory(); status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise RuntimeError('Cannot establish memory reserve')
    available = status.available_page / 1024 ** 3
    if available < 8:
        raise RuntimeError(f'Commit reserve is only {available:.3f} GiB; render not admitted')
    return available


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data', type=Path, default=Path('web/tournament-review/data.json'))
parser.add_argument('--output', type=Path, default=Path('deliverables/tournament-r11-stable.mp4'))
parser.add_argument('--preview-only', action='store_true')
args = parser.parse_args()
before = reserve()
data = json.loads(args.data.read_text(encoding='utf-8'))
args.output.parent.mkdir(parents=True, exist_ok=True)
W, H, FPS = 960, 540, 20
colors = ['#75ddff', '#ffb968', '#bca1ff', '#ff85b5', '#69e3b4', '#e5db88']
fonts = {n: ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', n) for n in [11, 12, 13, 15, 17, 20, 26, 30]}
groups = [g for g in data['groups'] if len(g['runs']) > 1]
times = {r['id']: [s[0] for s in r['samples']] for g in groups for r in g['runs']}


def sample(run, t):
    rows = run['samples']; i = max(0, bisect.bisect_right(times[run['id']], t) - 1)
    a, b = rows[i], rows[min(i + 1, len(rows) - 1)]
    f = 0 if a[0] == b[0] else max(0, min(1, (t - a[0]) / (b[0] - a[0])))
    result = [v + (b[k] - v) * f for k, v in enumerate(a)]
    result[3] = a[3] + math.atan2(math.sin(b[3] - a[3]), math.cos(b[3] - a[3])) * f
    return result


def frame(group, fraction, chapter):
    image = Image.new('RGB', (W, H), '#0a111a'); draw = ImageDraw.Draw(image)
    def text(x, y, value, n=13, fill='#dce8ef'):
        draw.text((x, y), value, font=fonts[n], fill=fill)
    text(24, 15, 'TERPS RACING / ENME408', 12, '#adf071')
    text(24, 38, 'Controller tournament / saved ghost replay', 26)
    text(24, 76, 'PRIOR STABLE R11 DATA  |  Not the new six-course campaign  |  Display interpolation only', 12, '#ffcf83')
    text(24, 103, f"{chapter + 1}/3  {group['label']}", 17)
    runs = group['runs']; eligible = [r for r in runs if r['accepted'] and r['selection_eligible']]
    winner = min(eligible, key=lambda r: r['time_s'])
    efficient = min(eligible, key=lambda r: r['energy_wh'])
    duration = max(r['samples'][-1][0] for r in runs); t = fraction * duration
    xs, ys = [p[0] for p in group['xy']], [p[1] for p in group['xy']]
    scale = min(550 / (max(xs) - min(xs)), 300 / (max(ys) - min(ys)))
    def pt(x, y):
        return 325 + (x - (max(xs) + min(xs)) / 2) * scale, 316 - (y - (max(ys) + min(ys)) / 2) * scale
    draw.rounded_rectangle((20, 136, 634, 484), 10, fill='#101e2a', outline='#2b4052')
    track = [pt(*p) for p in group['xy']]
    draw.line(track, fill='#344b5b', width=12, joint='curve')
    draw.line(track, fill='#728492', width=1, joint='curve')
    sx, sy = track[0]; text(sx + 6, sy - 17, 'START / FINISH', 11, '#a7b7c4')
    for i, run in enumerate(runs):
        row = sample(run, t); x, y = pt(row[1], row[2]); color = colors[i % len(colors)]
        if run['id'] == winner['id']:
            draw.ellipse((x - 16, y - 16, x + 16, y + 16), outline='#d5ff6b', width=3)
        angle = -row[3]
        body = [(12, -3), (12, 3), (-9, 5), (-9, -5)]
        points = [(x + a * math.cos(angle) - b * math.sin(angle), y + a * math.sin(angle) + b * math.cos(angle)) for a, b in body]
        draw.polygon(points, fill=color)
        for a, b in [(-6, -7), (-6, 7), (7, -7), (7, 7)]:
            tx, ty = x + a * math.cos(angle) - b * math.sin(angle), y + a * math.sin(angle) + b * math.cos(angle)
            draw.rectangle((tx - 2, ty - 2, tx + 2, ty + 2), fill='#050a10', outline=color)
        text(x + 17, y - 10 if i % 2 == 0 else y + 8, run['id'], 11, color)
        cy = 176 + i * 46
        text(658, cy, run['id'] + ('  * FASTEST' if run['id'] == winner['id'] else ''), 15, '#d5ff6b' if run['id'] == winner['id'] else color)
        energy = (run['samples'][0][6] - row[6]) / 3600
        lap = min(run['target_laps'], sum(l['finish_time_s'] <= t for l in run['laps']) + 1)
        text(658, cy + 18, f"lap {lap}/10 | {energy:.2f} Wh | {'FINISHED' if t >= run['time_s'] else f'{t:.1f} s'}", 11, '#a8bdcd')
        structure = run['policy']['structure']
        description = 'UNPAIRED / EXCLUDED FROM SELECTION' if not run['selection_eligible'] else f"{structure['drive']} / {structure['pedal']} / {structure['traction']} TC"
        text(658, cy + 31, description, 11, '#a8bdcd')
    text(658, 137, 'SYNCHRONIZED ELAPSED TIME', 12, '#a8bdcd')
    text(36, 149, f'{t:06.2f} / {duration:.2f} s  |  {duration / 12:.1f}x playback', 13, '#e2eff5')
    text(658, 462, '* criterion: fastest accepted round', 12, '#d5ff6b')
    text(24, 493, f"Fastest {winner['id']}: {winner['time_s']:.3f} s / {winner['energy_wh']:.3f} Wh", 13, '#d5ff6b')
    text(24, 514, f"Lowest energy {efficient['id']}: {efficient['time_s']:.3f} s / {efficient['energy_wh']:.3f} Wh", 12, '#a8bdcd')
    text(658, 485, '26 Oct 2026 | evidence 18:15 UTC', 11, '#a8bdcd')
    text(658, 501, 'Source 4e1eeaf / numerical bee54e7', 11, '#a8bdcd')
    text(658, 517, 'No universal or official-points winner.', 11, '#a8bdcd')
    return image


preview = args.output.with_suffix('.preview.png')
frame(groups[-1], .72, 2).save(preview)
if args.preview_only:
    print(json.dumps({'preview': str(preview), 'commit_headroom_gib': before})); raise SystemExit(0)
command = ['ffmpeg', '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-an', '-c:v', 'libx264', '-threads', '1', '-preset', 'veryfast', '-crf', '21', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(args.output)]
with args.output.with_suffix('.ffmpeg.log').open('w') as log:
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=log, creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == 'nt' else 0)
    try:
        for chapter, group in enumerate(groups):
            for i in range(12 * FPS):
                if i % FPS == 0: reserve()
                process.stdin.write(frame(group, i / (12 * FPS - 1), chapter).tobytes())
            for _ in range(2 * FPS):
                process.stdin.write(frame(group, 1, chapter).tobytes())
        process.stdin.close()
        if process.wait() != 0: raise RuntimeError('ffmpeg failed; inspect log')
    except BaseException:
        process.kill(); process.wait(); raise
receipt = {'video': str(args.output), 'bytes': args.output.stat().st_size, 'seconds': 42, 'fps': FPS, 'resolution': [W, H], 'chapters': [g['label'] for g in groups], 'source_commit': data['acceptance_commit'], 'numerical_checkpoint': data['numerical_checkpoint'], 'commit_headroom_before_gib': before, 'commit_headroom_after_gib': reserve(), 'scope': 'Earlier stable R11 data, synchronized saved poses, fastest criterion, excluded unpaired immigrant cannot win; not new six-course campaign.'}
args.output.with_suffix('.receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt))
