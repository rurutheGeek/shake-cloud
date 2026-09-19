#!/usr/bin/env python3
"""Generate a self-contained HTML page to review albums for every track.

Each row has a checkbox, editable album/genre/comment fields and the current
tags. Checks, inputs and comments are kept in the browser (localStorage) and
can be exported as a CSV for corrections. Run inside the tagger container:

  run --rm --entrypoint python3 tagger /tools/make-review-html.py
"""
import json
import os
from pathlib import Path

import mutagen

root = Path(os.environ.get('REVIEW_MUSIC', '/music'))
out = Path(os.environ.get('REVIEW_OUT', '/state/album-review.html'))
rows = []
for dirpath, dirnames, filenames in os.walk(root):
    if 'Converted' in Path(dirpath).parts or Path(dirpath).name.startswith('.'):
        continue
    for name in sorted(filenames):
        if not name.lower().endswith('.mp3'):
            continue
        path = Path(dirpath) / name
        tags = {}
        length = 0
        try:
            easy = mutagen.File(str(path), easy=True)
            if easy is not None and easy.tags is not None:
                for key in ('title', 'artist', 'album', 'albumartist', 'genre',
                            'composer'):
                    values = easy.tags.get(key)
                    if values:
                        tags[key] = str(values[0])
            audio = mutagen.File(str(path))
            if audio is not None:
                length = int(getattr(audio.info, 'length', 0) or 0)
        except Exception:  # noqa: BLE001
            pass
        rows.append({
            'path': str(path.relative_to(root)),
            'title': tags.get('title') or path.stem,
            'artist': tags.get('artist', ''),
            'album': tags.get('album', ''),
            'albumartist': tags.get('albumartist', ''),
            'genre': tags.get('genre', ''),
            'composer': tags.get('composer', ''),
            'length': length,
        })

page = '''<!doctype html><html lang="ja"><meta charset="utf-8">
<title>全曲アルバム確認</title>
<style>
body{font-family:sans-serif;font-size:13px;margin:12px;background:#161616;color:#d8d8d8}
table{border-collapse:collapse;width:100%;background:#1e1e1e}
th,td{border:1px solid #333;padding:2px 4px;text-align:left;vertical-align:top}
th{background:#2b2b2b;position:sticky;top:0}
td.path{font-family:monospace;font-size:11px;color:#888;max-width:320px;word-break:break-all}
td.small{font-size:11px;color:#999;max-width:160px;word-break:break-all}
td.comment input{width:100%}
td.comment div{display:flex;gap:4px;align-items:center}
input[type=text]{width:100%;box-sizing:border-box;font-size:12px;background:#111;color:#eee;border:1px solid #444}
tr.done{background:#20301f}
.bar{position:sticky;top:0;background:#161616;padding:6px 0;z-index:2;border-bottom:1px solid #333;margin-bottom:6px}
button{margin-right:8px;background:#333;color:#eee;border:1px solid #555;padding:3px 8px}
.count{color:#999}
a{color:#7ab7ff}
</style>
<div class="bar">
<input type="text" id="filter" placeholder="絞り込み（曲名・アルバム・パス）" style="width:320px">
<button onclick="exportCsv()">コメント付きのCSVをダウンロード</button>
<button onclick="clearAll()">入力を全部消す</button>
<span class="count" id="count"></span>
</div>
<table><colgroup>
<col style="width:16%"><col style="width:9%"><col style="width:12%"><col style="width:9%">
<col style="width:9%"><col style="width:25%"><col style="width:4%"><col style="width:16%">
</colgroup><thead><tr>
<th>曲名</th><th>アーティスト</th><th>アルバム</th><th>アルバムアーティスト</th>
<th>作曲者</th><th>コメント・指示</th><th>長さ</th><th>パス</th>
</tr></thead><tbody id="tbody"></tbody></table>
<script>
const DATA = __DATA__;
const KEY = 'album-review-v1';
let state = JSON.parse(localStorage.getItem(KEY) || '{}');
function save() { localStorage.setItem(KEY, JSON.stringify(state)); }
function cell(tag, text, cls) {
  const td = document.createElement(tag);
  if (cls) td.className = cls;
  td.textContent = text;
  return td;
}
function inputFor(row, field, placeholder) {
  const input = document.createElement('input');
  input.type = 'text';
  input.placeholder = placeholder || '';
  input.value = (state[row.path] && state[row.path][field]) || '';
  input.addEventListener('input', () => {
    state[row.path] = state[row.path] || {};
    state[row.path][field] = input.value;
    save();
  });
  return input;
}
function render() {
  const filter = document.getElementById('filter').value.toLowerCase();
  const tbody = document.getElementById('tbody');
  tbody.innerHTML = '';
  let shown = 0, commented = 0;
  for (const row of DATA) {
    const st = state[row.path] || {};
    if ((st.comment || '').trim()) commented++;
    const haystack = (row.title + ' ' + row.artist + ' ' + row.album + ' ' + row.path).toLowerCase();
    if (filter && !haystack.includes(filter)) continue;
    shown++;
    const tr = document.createElement('tr');
    if ((st.comment || '').trim()) tr.className = 'done';
    const tdTitle = document.createElement('td');
    tdTitle.textContent = row.title;
    const copy = document.createElement('button');
    copy.textContent = 'コピー';
    copy.style.fontSize = '11px';
    copy.addEventListener('click', () => {
      const text = row.title;
      if (navigator.clipboard) { navigator.clipboard.writeText(text); }
      else { window.prompt('コピーしてください', text); }
    });
    tdTitle.appendChild(document.createTextNode(' '));
    tdTitle.appendChild(copy);
    tr.appendChild(tdTitle);
    tr.appendChild(cell('td', row.artist, 'small'));
    tr.appendChild(cell('td', row.album, 'small'));
    tr.appendChild(cell('td', row.albumartist, 'small'));
    tr.appendChild(cell('td', row.composer, 'small'));
    const tdComment = document.createElement('td'); tdComment.className = 'comment';
    const commentWrap = document.createElement('div');
    const commentInput = inputFor(row, 'comment', '指示など');
    const paste = document.createElement('button');
    paste.textContent = '貼り付け';
    paste.style.fontSize = '11px';
    paste.addEventListener('click', async () => {
      let text = '';
      try {
        text = await navigator.clipboard.readText();
      } catch (error) {
        text = '';
      }
      if (text) {
        commentInput.value = text;
        state[row.path] = state[row.path] || {};
        state[row.path].comment = text;
        save(); render();
      } else {
        commentInput.focus();
        commentInput.select();
        commentInput.placeholder = 'Ctrl+Vで貼り付けてください';
        setTimeout(() => { commentInput.placeholder = '指示など'; }, 4000);
      }
    });
    commentWrap.appendChild(commentInput);
    commentWrap.appendChild(paste);
    tdComment.appendChild(commentWrap);
    tr.appendChild(tdComment);
    tr.appendChild(cell('td', row.length + 's'));
    tr.appendChild(cell('td', row.path, 'path'));
    tbody.appendChild(tr);
  }
  document.getElementById('count').textContent = shown + '曲表示 / コメント' + commented + '曲';
}
function csvCell(value) {
  const text = String(value == null ? '' : value);
  return /[",\\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
}
function exportCsv() {
  const lines = [['path','title','artist','album','albumartist','composer','comment'].join(',')];
  for (const row of DATA) {
    const st = state[row.path] || {};
    if (!(st.comment || '').trim()) continue;
    lines.push([row.path, row.title, row.artist, row.album, row.albumartist,
                row.composer, st.comment || ''].map(csvCell).join(','));
  }
  const blob = new Blob(['\\ufeff' + lines.join('\\r\\n')], {type: 'text/csv;charset=utf-8'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'album-review.csv';
  link.click();
}
function clearAll() {
  if (!confirm('入力を全部消しますか？')) return;
  state = {}; save(); render();
}
document.getElementById('filter').addEventListener('input', render);
render();
</script>
</html>'''
page = page.replace('__DATA__', json.dumps(rows, ensure_ascii=False).replace('<', '\\u003c'))
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(page, encoding='utf-8')
print(f'tracks={len(rows)} out={out}')
