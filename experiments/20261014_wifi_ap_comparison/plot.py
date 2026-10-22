#!/usr/bin/env python3
"""results-server.csv から比較グラフ（comparison.svg）を作る。

    python3 experiments/20261014_wifi_ap_comparison/plot.py

端末・地点・AP・帯域・方向ごとの中央値を棒にする。色は AP と帯域の組（系列）に
固定で、値は棒の上に書く（色だけに頼らない）。
"""
import collections
import csv
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERIES = [('aterm', '5GHz', 'Aterm 5GHz', 's1'), ('flint3', '5GHz', 'Flint 3 5GHz', 's2'),
          ('flint3', '6GHz', 'Flint 3 6GHz', 's3')]
DEVICES = [('lenovo-ac9560', 'レノボ'), ('nec-ax210', 'NEC'),
           ('s23-ultra', 'S23 Ultra'), ('z-flip8', 'Z Flip8')]
PANELS = [('ap-room', 'down', '同じ部屋・下り'), ('ap-room', 'up', '同じ部屋・上り'),
          ('toilet', 'down', 'トイレ・下り'), ('toilet', 'up', 'トイレ・上り')]
W, H, PAD_L, PAD_T, PLOT_H = 470, 250, 46, 34, 150
BAR, GAP, GROUP_GAP = 22, 2, 26


def medians():
    values = collections.defaultdict(list)
    with open(HERE / 'results-server.csv', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            key = (row['location'], row['direction'], row['device'], row['ap'], row['band'])
            values[key].append(float(row['mbps']))
    return {key: statistics.median(items) for key, items in values.items()}


def panel(data, location, direction, title, x0, y0, top):
    out = [f'<g transform="translate({x0},{y0})">',
           f'<text class="title" x="0" y="14">{title}</text>']
    for tick in range(0, top + 1, top // 4):
        y = PAD_T + PLOT_H - PLOT_H * tick / top
        out.append(f'<line class="grid" x1="{PAD_L}" x2="{W - 8}" y1="{y:.1f}" y2="{y:.1f}"/>')
        out.append(f'<text class="axis" x="{PAD_L - 6}" y="{y + 4:.1f}" text-anchor="end">{tick}</text>')
    x = PAD_L + 10
    for device, label in DEVICES:
        bars = [(name, css, data.get((location, direction, device, ap, band)))
                for ap, band, name, css in SERIES]
        bars = [bar for bar in bars if bar[2] is not None]
        if not bars:
            continue
        start = x
        for name, css, value in bars:
            height = PLOT_H * value / top
            y = PAD_T + PLOT_H - height
            out.append(
                f'<path class="{css}" d="M{x},{PAD_T + PLOT_H} V{y + 4:.1f} q0,-4 4,-4 h{BAR - 8} q4,0 4,4 '
                f'V{PAD_T + PLOT_H} Z"><title>{label} / {name} / {title}: {value:g} Mbps</title></path>')
            out.append(f'<text class="value" x="{x + BAR / 2}" y="{y - 4:.1f}" text-anchor="middle">{value:.0f}</text>')
            x += BAR + GAP
        out.append(f'<text class="axis" x="{(start + x - GAP) / 2:.1f}" y="{PAD_T + PLOT_H + 16}" text-anchor="middle">{label}</text>')
        x += GROUP_GAP
    out.append(f'<line class="base" x1="{PAD_L}" x2="{W - 8}" y1="{PAD_T + PLOT_H}" y2="{PAD_T + PLOT_H}"/>')
    out.append('</g>')
    return out


def main():
    data = medians()
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W * 2 + 20} {H * 2 + 70}" '
           'font-family="system-ui, sans-serif" role="img" '
           'aria-label="Aterm と Flint 3 の無線スループット比較（Mbps）">',
           '<style>',
           '.bg{fill:#fcfcfb}.title{font-size:13px;font-weight:600;fill:#0b0b0b}'
           '.head{font-size:15px;font-weight:600;fill:#0b0b0b}.axis,.legend{font-size:11px;fill:#52514e}'
           '.value{font-size:10px;fill:#0b0b0b}.grid{stroke:#e4e3df;stroke-width:1}.base{stroke:#8a897f;stroke-width:1}'
           '.s1{fill:#2a78d6}.s2{fill:#eb6834}.s3{fill:#1baf7a}',
           '@media (prefers-color-scheme: dark){.bg{fill:#1a1a19}.title,.head,.value{fill:#fff}'
           '.axis,.legend{fill:#c3c2b7}.grid{stroke:#383835}.base{stroke:#8a897f}'
           '.s1{fill:#3987e5}.s2{fill:#d95926}.s3{fill:#199e70}}',
           '</style>',
           f'<rect class="bg" width="{W * 2 + 20}" height="{H * 2 + 70}"/>',
           '<text class="head" x="16" y="24">無線スループットの比較（Mbps、iperf3 4並列30秒の中央値）</text>']
    x = 16
    for _, _, name, css in SERIES:
        svg.append(f'<rect class="{css}" x="{x}" y="36" width="12" height="12" rx="2"/>')
        svg.append(f'<text class="legend" x="{x + 17}" y="46">{name}</text>')
        x += 120
    for index, (location, direction, title) in enumerate(PANELS):
        top = 2000 if location == 'ap-room' else 800
        svg += panel(data, location, direction, title, 10 + (index % 2) * (W + 10), 60 + (index // 2) * H, top)
    svg.append('</svg>')
    (HERE / 'comparison.svg').write_text('\n'.join(svg) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
