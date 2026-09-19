#!/usr/bin/env python3
"""Build lyrics pages: one listing tracks that have .lrc, one for manual input.

Outputs /state/lyrics-found.html and /state/lyrics-missing.html. The missing
page has a textarea per track and exports a CSV (path,lyrics) for tracks that
were filled in, so the server can write the .lrc sidecars.
"""
import json
import os
from pathlib import Path

import mutagen

ROOT = Path('/music')
OUT_FOUND = Path('/state/lyrics-found.html')
OUT_MISSING = Path('/state/lyrics-missing.html')
SKIP_GENRES = {'Soundtrack', 'Game', 'Classical', 'Chiptune', 'Arrange', 'Electronic',
               'Dance', 'Instrumental'}
SKIP_ALBUM = ('サウンドトラック', 'Original Soundtrack', 'OST', 'サントラ', 'スーパーミュージック',
              'ゲーム音源', 'ピアノ', 'オルゴール', 'ミュージックコレクション', 'Music Collection',
              'Soundtrack', 'クラシック', 'Concert', '狩猟音楽祭')

found = []
missing = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    if 'Converted' in Path(dirpath).parts:
        continue
    for name in filenames:
        if not name.lower().endswith('.mp3'):
            continue
        path = Path(dirpath) / name
        tags = {}
        length = 0
        try:
            easy = mutagen.File(str(path), easy=True)
            if easy and easy.tags:
                for key in ('title', 'artist', 'album', 'genre'):
                    v = easy.tags.get(key)
                    if v:
                        tags[key] = str(v[0])
            audio = mutagen.File(str(path))
            if audio:
                length = int(getattr(audio.info, 'length', 0) or 0)
        except Exception:
            pass
        rel = str(path.relative_to(ROOT))
        has_lrc = path.with_suffix('.lrc').exists()
        row = {'path': rel, 'title': tags.get('title') or path.stem,
               'artist': tags.get('artist', ''), 'album': tags.get('album', ''),
               'genre': tags.get('genre', ''), 'length': length}
        if has_lrc:
            found.append(row)
            continue
        genre = tags.get('genre', '')
        album = tags.get('album', '')
        if genre in SKIP_GENRES or genre == '':
            continue
        if any(word.lower() in album.lower() for word in SKIP_ALBUM):
            continue
        missing.append(row)


def export_script(fields, filename):
    return f'''function csvCell(v){{const t=String(v==null?'':v);return /[",\\n]/.test(t)?'"'+t.replace(/"/g,'""')+'"':t;}}
function exportCsv(){{
  const lines=[{','.join(repr(f) for f in fields)}.join(',')];
  for(const row of DATA.rows){{const st=state[row.path]||{{}};
    const values={fields}.map(f=>f==='lyrics'?(st.lyrics||''):row[f]);
    if(fields.includes('lyrics') && !(st.lyrics||'').trim()) continue;
    lines.push(values.map(csvCell).join(','));}}
  const blob=new Blob(['\\ufeff'+lines.join('\\r\\n')],{{type:'text/csv;charset=utf-8'}});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download={repr(filename)};a.click();
}}'''


def page(title, intro, fields, columns, rows, filename, editable=False):
    data = json.dumps({'rows': rows}, ensure_ascii=False).replace('<', '\\u003c')
    heads = ''.join(f'<th>{c}</th>' for c in columns)
    result = f'''<!doctype html><html lang="ja"><meta charset="utf-8">
<title>{title}</title>
<style>
body{{font-family:sans-serif;font-size:13px;margin:12px;background:#161616;color:#d8d8d8}}
table{{border-collapse:collapse;width:100%;background:#1e1e1e}}
th,td{{border:1px solid #333;padding:2px 4px;text-align:left;vertical-align:top}}
th{{background:#2b2b2b;position:sticky;top:0}}
td.path{{font-family:monospace;font-size:11px;color:#888;word-break:break-all;max-width:260px}}
td.small{{font-size:11px;color:#999}}
textarea{{width:100%;box-sizing:border-box;background:#111;color:#eee;border:1px solid #444;font-size:12px}}
input[type=text]{{background:#111;color:#eee;border:1px solid #444;width:260px}}
.bar{{position:sticky;top:0;background:#161616;padding:6px 0;border-bottom:1px solid #333;margin-bottom:6px;z-index:2}}
button{{background:#333;color:#eee;border:1px solid #555;padding:3px 8px;margin-right:6px}}
</style>
<div class="bar"><input type="text" id="filter" placeholder="絞り込み">
<button onclick="exportCsv()">CSVをダウンロード</button><span id="count" style="color:#999"></span></div>
<p>{intro}</p>
<table><thead><tr>{heads}</tr></thead><tbody id="tbody"></tbody></table>
<script>
const DATA=__DATA__;
const KEY={repr('lyrics-v1-' + filename)};
let state=JSON.parse(localStorage.getItem(KEY)||'{{}}');
function save(){{localStorage.setItem(KEY,JSON.stringify(state));}}
function cell(tag,text,cls){{const el=document.createElement(tag);if(cls)el.className=cls;el.textContent=text;return el;}}
function render(){{
  const tbody=document.getElementById('tbody');tbody.innerHTML='';
  const filter=document.getElementById('filter').value.toLowerCase();
  let shown=0,filled=0;
  for(const row of DATA.rows){{
    const st=state[row.path]||{{}};
    if((st.lyrics||'').trim())filled++;
    if(filter && !(row.title+row.artist+row.path).toLowerCase().includes(filter))continue;
    shown++;
    const tr=document.createElement('tr');
    tr.appendChild(cell('td',row.title));
    tr.appendChild(cell('td',row.artist,'small'));
    tr.appendChild(cell('td',row.genre,'small'));
    tr.appendChild(cell('td',row.length+'s','small'));
    if({str(editable).lower()}){{
      const td=document.createElement('td');
      const area=document.createElement('textarea');
      area.rows=4;area.value=st.lyrics||'';
      area.addEventListener('input',()=>{{state[row.path]=state[row.path]||{{}};state[row.path].lyrics=area.value;save();}});
      td.appendChild(area);tr.appendChild(td);
    }}
    tr.appendChild(cell('td',row.path,'path'));
    tbody.appendChild(tr);
  }}
  document.getElementById('count').textContent=shown+'曲表示' + ({str(editable).lower()} ? ' / 入力'+filled+'曲' : '');
}}
{export_script(fields, filename)}
document.getElementById('filter').addEventListener('input',render);
render();
</script></html>'''
    return result.replace('__DATA__', data)


OUT_FOUND.write_text(page(
    '歌詞あり一覧', '歌詞（.lrc）が取得できている曲の一覧です。',
    ['path', 'title', 'artist', 'album', 'genre'],
    ['曲名', 'アーティスト', 'ジャンル', '長さ', 'パス'],
    [{'path': r['path'], 'title': r['title'], 'artist': r['artist'],
      'album': r['album'], 'genre': r['genre'], 'length': r['length']} for r in found],
    'lyrics-found.csv'))

OUT_MISSING.write_text(page(
    '歌詞を入力（見つからなかった曲）',
    '歌詞が見つからなかった曲です。入力した行だけCSVで出力できます（このCSVを送れば.lrcとして配置します）。',
    ['path', 'title', 'artist', 'genre', 'lyrics'],
    ['曲名', 'アーティスト', 'ジャンル', '長さ', '歌詞', 'パス'],
    missing, 'lyrics-missing.csv', editable=True))

print('found', len(found), 'missing', len(missing))
