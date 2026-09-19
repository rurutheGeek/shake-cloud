#!/usr/bin/env python3
"""Generate a page to review album covers with their metadata.

Groups tracks by album, copies each album folder's cover image next to the
page and renders a card grid: cover, album, albumartist, year, track count and
folder. Flags and comments are kept in the browser and exported as CSV.

Run inside the tagger container:

  run --rm --entrypoint python3 tagger /tools/make-cover-review.py
"""
import collections
import json
import os
import shutil
from pathlib import Path

import mutagen

ROOT = Path(os.environ.get('COVER_REVIEW_MUSIC', '/music'))
OUT = Path(os.environ.get('COVER_REVIEW_OUT', '/state/cover-review'))
COVER_NAMES = ('cover.jpg', 'cover.jpeg', 'cover.png')


def find_cover(folder):
    for candidate in (folder, folder.parent, folder.parent.parent):
        for name in COVER_NAMES:
            path = candidate / name
            if path.is_file():
                return path
    return None


albums = {}
for dirpath, dirnames, filenames in os.walk(ROOT):
    if 'Converted' in Path(dirpath).parts:
        continue
    for name in sorted(filenames):
        if not name.lower().endswith('.mp3'):
            continue
        path = Path(dirpath) / name
        tags = {}
        try:
            easy = mutagen.File(str(path), easy=True)
            if easy is not None and easy.tags is not None:
                for key in ('album', 'albumartist', 'genre', 'date'):
                    values = easy.tags.get(key)
                    if values:
                        tags[key] = str(values[0])
        except Exception:  # noqa: BLE001
            pass
        album = tags.get('album') or Path(dirpath).name
        albumartist = tags.get('albumartist') or Path(dirpath).parent.name
        key = (albumartist, album)
        entry = albums.setdefault(key, {
            'album': album,
            'albumartist': albumartist,
            'genre': tags.get('genre', ''),
            'dates': collections.Counter(),
            'folders': collections.Counter(),
            'tracks': 0,
        })
        entry['tracks'] += 1
        if tags.get('date'):
            entry['dates'][tags['date'][:4]] += 1
        entry['folders'][str(path.parent.relative_to(ROOT))] += 1

rows = []
covers_dir = OUT / 'covers'
if covers_dir.exists():
    shutil.rmtree(covers_dir)
covers_dir.mkdir(parents=True)
for index, ((albumartist, album), entry) in enumerate(
        sorted(albums.items(), key=lambda item: (item[0][0].lower(), item[0][1].lower()))):
    folder = entry['folders'].most_common(1)[0][0]
    source = find_cover(ROOT / folder)
    cover = ''
    if source is not None:
        suffix = '.png' if source.suffix.lower() == '.png' else '.jpg'
        filename = f'{index + 1:04d}{suffix}'
        shutil.copy(source, covers_dir / filename)
        cover = f'covers/{filename}'
    rows.append({
        'album': album,
        'albumartist': albumartist,
        'genre': entry['genre'],
        'year': (entry['dates'].most_common(1)[0][0] if entry['dates'] else ''),
        'tracks': entry['tracks'],
        'folder': folder,
        'cover': cover,
    })

page = '''<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>アルバム画像チェック</title>
<style>
body{font-family:sans-serif;font-size:13px;margin:12px;background:#161616;color:#d8d8d8}
.bar{position:sticky;top:0;background:#161616;padding:6px 0;z-index:2;border-bottom:1px solid #333;margin-bottom:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
input[type=text]{background:#111;color:#eee;border:1px solid #444;font-size:12px;padding:3px 6px}
button,select{background:#333;color:#eee;border:1px solid #555;padding:3px 8px}
a{color:#7ab7ff}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}
.card{background:#1e1e1e;border:1px solid #333;padding:8px;display:flex;gap:8px}
.card.flagged{border-color:#c07000;background:#2a2113}
.card img{width:110px;height:110px;object-fit:cover;background:#000;flex:none;cursor:zoom-in}
.card .noimg{width:110px;height:110px;flex:none;background:#000;color:#666;display:flex;align-items:center;justify-content:center;font-size:11px;text-align:center}
.card .meta{min-width:0}
.card .album{font-weight:bold;word-break:break-all}
.card .sub{color:#aaa;font-size:11px;word-break:break-all}
.card .path{color:#666;font-size:10px;font-family:monospace;word-break:break-all}
.card .comment{display:flex;gap:4px;margin-top:4px}
.card .comment input{width:100%}
.card label{font-size:11px;color:#c9a227;user-select:none}
#count{color:#999}
dialog{background:#111;border:1px solid #555;padding:0}
dialog img{max-width:90vw;max-height:90vh;display:block}
</style>
<div class="bar">
<input type="text" id="filter" placeholder="絞り込み（アルバム・アーティスト・パス）" style="width:280px">
<select id="mode">
<option value="all">すべて</option>
<option value="flagged">指摘済みだけ</option>
<option value="nocover">画像なしだけ</option>
</select>
<button onclick="exportCsv()">指摘CSVをダウンロード</button>
<button onclick="clearAll()">入力を全部消す</button>
<a href="index.html">曲ごとのアルバム確認へ</a>
<span id="count"></span>
</div>
<div class="grid" id="grid"></div>
<dialog id="zoom"><img id="zoomimg" alt=""></dialog>
<script>
const DATA = __DATA__;
const KEY = 'cover-review-v1';
let state = JSON.parse(localStorage.getItem(KEY) || '{}');
function save() { localStorage.setItem(KEY, JSON.stringify(state)); }
function render() {
  const filter = document.getElementById('filter').value.toLowerCase();
  const mode = document.getElementById('mode').value;
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  let shown = 0, flagged = 0, nocover = 0;
  for (const row of DATA) {
    const st = state[row.folder] || {};
    if (st.flag || (st.comment || '').trim()) flagged++;
    if (!row.cover) nocover++;
    if (mode === 'flagged' && !(st.flag || (st.comment || '').trim())) continue;
    if (mode === 'nocover' && row.cover) continue;
    const haystack = (row.album + ' ' + row.albumartist + ' ' + row.folder).toLowerCase();
    if (filter && !haystack.includes(filter)) continue;
    shown++;
    const card = document.createElement('div');
    card.className = 'card' + ((st.flag || (st.comment || '').trim()) ? ' flagged' : '');
    if (row.cover) {
      const img = document.createElement('img');
      img.src = row.cover; img.loading = 'lazy'; img.alt = row.album;
      img.addEventListener('click', () => {
        document.getElementById('zoomimg').src = row.cover;
        document.getElementById('zoom').showModal();
      });
      card.appendChild(img);
    } else {
      const div = document.createElement('div');
      div.className = 'noimg'; div.textContent = '画像なし';
      card.appendChild(div);
    }
    const meta = document.createElement('div');
    meta.className = 'meta';
    const album = document.createElement('div');
    album.className = 'album'; album.textContent = row.album;
    const sub = document.createElement('div');
    sub.className = 'sub';
    sub.textContent = row.albumartist + (row.year ? ' / ' + row.year : '') +
      ' / ' + row.tracks + '曲' + (row.genre ? ' / ' + row.genre : '');
    const path = document.createElement('div');
    path.className = 'path'; path.textContent = row.folder;
    meta.appendChild(album); meta.appendChild(sub); meta.appendChild(path);
    const label = document.createElement('label');
    const flag = document.createElement('input');
    flag.type = 'checkbox'; flag.checked = !!st.flag;
    flag.addEventListener('change', () => {
      state[row.folder] = state[row.folder] || {};
      state[row.folder].flag = flag.checked;
      save(); render();
    });
    label.appendChild(flag);
    label.appendChild(document.createTextNode(' 要修正'));
    meta.appendChild(label);
    const wrap = document.createElement('div');
    wrap.className = 'comment';
    const input = document.createElement('input');
    input.type = 'text'; input.placeholder = '正しい画像・アルバム名など';
    input.value = st.comment || '';
    input.addEventListener('input', () => {
      state[row.folder] = state[row.folder] || {};
      state[row.folder].comment = input.value;
      save();
    });
    wrap.appendChild(input);
    meta.appendChild(wrap);
    card.appendChild(meta);
    grid.appendChild(card);
  }
  document.getElementById('count').textContent =
    shown + '件表示 / 指摘' + flagged + '件 / 画像なし' + nocover + '件';
}
function csvCell(value) {
  const text = String(value == null ? '' : value);
  return /[",\\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
}
function exportCsv() {
  const lines = [['albumartist','album','year','genre','tracks','folder','flag','comment'].join(',')];
  for (const row of DATA) {
    const st = state[row.folder] || {};
    if (!(st.flag || (st.comment || '').trim())) continue;
    lines.push([row.albumartist, row.album, row.year, row.genre, row.tracks,
                row.folder, st.flag ? '1' : '', st.comment || ''].map(csvCell).join(','));
  }
  const blob = new Blob(['\\ufeff' + lines.join('\\r\\n')], {type: 'text/csv;charset=utf-8'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'cover-review.csv';
  link.click();
}
function clearAll() {
  if (!confirm('入力を全部消しますか？')) return;
  state = {}; save(); render();
}
document.getElementById('filter').addEventListener('input', render);
document.getElementById('mode').addEventListener('change', render);
document.getElementById('zoom').addEventListener('click', function () { this.close(); });
render();
</script>
</html>'''
page = page.replace('__DATA__', json.dumps(rows, ensure_ascii=False).replace('<', '\\u003c'))
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'covers.html').write_text(page, encoding='utf-8')
with_cover = sum(1 for row in rows if row['cover'])
print(f'albums={len(rows)} with_cover={with_cover} out={OUT / "covers.html"}')
