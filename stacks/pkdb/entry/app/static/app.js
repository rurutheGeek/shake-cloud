/* ポケモンDB管理の小さな動き。依存ライブラリなし。 */
(function () {
  'use strict';

  /* ---- 表示テーマ ---- */
  var root = document.documentElement;
  var toggle = document.getElementById('theme-toggle');
  var ORDER = ['auto', 'light', 'dark'];
  var LABEL = { auto: 'OSに合わせる', light: 'ライト', dark: 'ダーク' };
  function applyTheme(choice) {
    root.dataset.theme = choice;
    if (toggle) { toggle.title = '表示テーマ: ' + LABEL[choice]; }
  }
  if (toggle) {
    toggle.addEventListener('click', function () {
      var current = 'auto';
      try { current = localStorage.getItem('pkdb-theme') || 'auto'; } catch (e) { /* 保存できない環境 */ }
      var next = ORDER[(ORDER.indexOf(current) + 1) % ORDER.length];
      try { localStorage.setItem('pkdb-theme', next); } catch (e) { /* 保存できない環境 */ }
      applyTheme(next);
    });
  }

  /* ---- 成功メッセージは少ししたら消す ---- */
  window.setTimeout(function () {
    document.querySelectorAll('.flash.ok').forEach(function (element) { element.remove(); });
  }, 15000);

  /* ---- 確認つきの送信 ---- */
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (form && form.dataset && form.dataset.confirm) {
      if (!window.confirm(form.dataset.confirm)) { event.preventDefault(); }
    }
  });

  /* ---- 種族値の合計を出す ---- */
  document.querySelectorAll('.stat-inputs').forEach(function (box) {
    var output = box.parentElement.querySelector('[data-stat-total]');
    if (!output) { return; }
    var inputs = box.querySelectorAll('input');
    var update = function () {
      var total = 0;
      inputs.forEach(function (input) { total += Number(input.value) || 0; });
      output.textContent = total ? String(total) : '—';
    };
    inputs.forEach(function (input) { input.addEventListener('input', update); });
    update();
  });

  /* ---- 全体検索 ---- */
  var searchInput = document.getElementById('global-search');
  var searchBox = document.getElementById('search-results');
  if (searchInput && searchBox) {
    var timer = null;
    var items = [];
    var active = -1;

    function close() {
      searchBox.hidden = true;
      searchBox.innerHTML = '';
      items = [];
      active = -1;
    }

    function link(kind, id, title, sub, href) {
      var anchor = document.createElement('a');
      anchor.href = href;
      anchor.dataset.index = String(items.length);
      var strong = document.createElement('span');
      strong.className = 'title';
      strong.textContent = title;
      anchor.appendChild(strong);
      if (sub) {
        var small = document.createElement('span');
        small.className = 'dim';
        small.textContent = sub;
        anchor.appendChild(small);
      }
      var badge = document.createElement('span');
      badge.className = 'kind';
      badge.textContent = kind;
      anchor.appendChild(badge);
      items.push(anchor);
      return anchor;
    }

    function render(data) {
      searchBox.innerHTML = '';
      items = [];
      active = -1;
      var total = 0;
      if (data.pokemon && data.pokemon.length) {
        searchBox.appendChild(groupTitle('ポケモン'));
        data.pokemon.forEach(function (row) {
          searchBox.appendChild(link('ポケモン', row.ndex_number, row.ndex_number + ' ' + row.name, '', '/pokemon/' + row.ndex_number));
          total += 1;
        });
      }
      if (data.moves && data.moves.length) {
        searchBox.appendChild(groupTitle('わざ'));
        data.moves.forEach(function (row) {
          searchBox.appendChild(link('わざ', row.move_id, row.name, '', '/moves/' + row.move_id));
          total += 1;
        });
      }
      if (data.abilities && data.abilities.length) {
        searchBox.appendChild(groupTitle('特性'));
        data.abilities.forEach(function (row) {
          searchBox.appendChild(link('特性', row.ability_id, row.name, '', '/abilities/' + row.ability_id));
          total += 1;
        });
      }
      if (!total) {
        var empty = document.createElement('div');
        empty.className = 'empty';
        empty.textContent = '見つかりません。「ポケモン一覧」から探せます。';
        searchBox.appendChild(empty);
      } else {
        var all = document.createElement('a');
        all.href = '/pokemon?q=' + encodeURIComponent(searchInput.value.trim());
        all.textContent = 'ポケモンの一覧で「' + searchInput.value.trim() + '」をしぼる';
        all.className = 'kind';
        searchBox.appendChild(all);
      }
      searchBox.hidden = false;
    }

    function groupTitle(text) {
      var div = document.createElement('div');
      div.className = 'group-title';
      div.textContent = text;
      return div;
    }

    function move(delta) {
      if (!items.length) { return; }
      active = (active + delta + items.length) % items.length;
      items.forEach(function (item, index) { item.classList.toggle('active', index === active); });
      items[active].scrollIntoView({ block: 'nearest' });
    }

    searchInput.addEventListener('input', function () {
      var term = searchInput.value.trim();
      window.clearTimeout(timer);
      if (term.length < 1) { close(); return; }
      timer = window.setTimeout(function () {
        fetch('/api/search?q=' + encodeURIComponent(term), { headers: { Accept: 'application/json' } })
          .then(function (response) { return response.json(); })
          .then(render)
          .catch(close);
      }, 150);
    });

    searchInput.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowDown') { event.preventDefault(); move(1); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); move(-1); }
      else if (event.key === 'Enter' && active >= 0 && items[active]) { window.location = items[active].href; }
      else if (event.key === 'Escape') { close(); }
    });

    document.addEventListener('click', function (event) {
      if (!searchBox.contains(event.target) && event.target !== searchInput) { close(); }
    });
  }

  /* ---- 覚えわざの表 ---- */
  var rows = document.getElementById('learnset-rows');
  var template = document.getElementById('row-template');
  if (rows && template) {
    var nextIndex = rows.querySelectorAll('.learn-row').length;

    function addRow(values) {
      var html = template.innerHTML.replace(/__i__/g, String(nextIndex));
      var holder = document.createElement('tbody');
      holder.innerHTML = html.trim();
      var row = holder.firstElementChild;
      if (values) {
        var move = row.querySelector('input[name^=move_name]');
        var level = row.querySelector('input[name^=level]');
        var method = row.querySelector('select[name^=method_name]');
        if (move && values.move) { move.value = values.move; }
        if (level && values.level !== null && values.level !== undefined) { level.value = values.level; }
        if (method && values.method) { method.value = values.method; }
      }
      var remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'link-button danger remove-row';
      remove.textContent = 'この行を消す';
      var cell = row.lastElementChild;
      cell.innerHTML = '';
      cell.appendChild(remove);
      rows.appendChild(row);
      nextIndex += 1;
      if (values && values.focus) { row.querySelector('input[name^=move_name]').focus(); }
      return row;
    }

    var addButton = document.getElementById('add-row');
    if (addButton) {
      addButton.addEventListener('click', function () { addRow({ focus: true }); });
    }
    rows.addEventListener('click', function (event) {
      if (event.target.classList.contains('remove-row')) {
        var row = event.target.closest('tr');
        var learnId = row.querySelector('input[name^=learn_id]');
        if (learnId && learnId.value) {
          var check = row.querySelector('input[name^=delete_]');
          if (check) { check.checked = true; }
          row.style.display = 'none';
        } else {
          row.remove();
        }
      }
    });

    var bulkButton = document.getElementById('bulk-add-button');
    if (bulkButton) {
      bulkButton.addEventListener('click', function () {
        var text = document.getElementById('bulk-text').value;
        var method = document.getElementById('bulk-method').value;
        var count = 0;
        text.split('\n').forEach(function (line) {
          line = line.trim();
          if (!line || line.charAt(0) === '#') { return; }
          var parts = line.split(/[\s,、\t]+/).filter(Boolean);
          var level = null;
          if (parts.length > 1 && /^\d{1,3}$/.test(parts[parts.length - 1])) {
            level = parts.pop();
          }
          if (!parts.length) { return; }
          addRow({ move: parts.join(' '), level: level, method: method });
          count += 1;
        });
        if (count) { document.getElementById('bulk-text').value = ''; }
      });
    }
  }
})();
