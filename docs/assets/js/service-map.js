// サービス図（docs/service-map.md）。データは service-map-data.js。
(function () {
  var root = document.getElementById('service-map');
  if (!root || !window.SERVICE_MAP) return;
  var data = window.SERVICE_MAP;
  // ページは <site>/service-map/ に出る。手順書へのリンクはサイトの根から数える。
  var base = root.getAttribute('data-base') || '../';
  var kinds = { base: '基盤VM', cloud: 'クラウドVM', host: 'ホスト' };

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      if (key === 'text') node.textContent = attrs[key];
      else node.setAttribute(key, attrs[key]);
    });
    (children || []).forEach(function (child) { if (child) node.appendChild(child); });
    return node;
  }

  var search = el('input', { type: 'search', placeholder: '絞り込み（例: nextcloud、音楽、監視）', 'aria-label': '絞り込み' });
  var grid = el('div', { class: 'sm-grid' });
  var detail = el('aside', { class: 'sm-detail', 'aria-live': 'polite' });
  var legend = el('div', { class: 'sm-legend' }, Object.keys(kinds).map(function (kind) {
    return el('span', { class: 'sm-kind sm-' + kind, text: kinds[kind] });
  }));
  root.appendChild(el('div', { class: 'sm-toolbar' }, [search, legend]));
  root.appendChild(el('div', { class: 'sm-layout' }, [grid, detail]));

  var chips = [];
  var cards = {};
  var selected = null;

  function links(docs) {
    if (!docs || !docs.length) return null;
    return el('ul', { class: 'sm-docs' }, docs.map(function (doc) {
      return el('li', {}, [el('a', { href: base + doc.path, text: doc.title })]);
    }));
  }

  function row(label, value) {
    if (!value) return null;
    return el('div', { class: 'sm-row' }, [el('span', { class: 'sm-label', text: label }),
      typeof value === 'string' ? el('span', { text: value }) : value]);
  }

  function highlight(names) {
    Object.keys(cards).forEach(function (name) {
      cards[name].classList.toggle('sm-on-route', names.indexOf(name) >= 0);
    });
  }

  function showService(vm, service, chip) {
    if (selected) selected.classList.remove('sm-selected');
    selected = chip;
    chip.classList.add('sm-selected');
    var route = null;
    if (service.route) {
      var hops = ['端末'].concat(service.route).concat([service.upstream]);
      route = el('span', { class: 'sm-route' }, hops.map(function (hop) {
        return el('span', { class: 'sm-hop', text: hop });
      }));
    }
    highlight(service.route || [vm.name]);
    detail.replaceChildren(
      el('h3', { text: service.name }),
      service.description ? el('p', { text: service.description }) : null,
      service.url ? el('p', {}, [el('a', { class: 'sm-open', href: service.url, text: service.url })]) : null,
      row('VM', vm.name),
      row('経路', route),
      row('ログイン', service.route ? (service.sso ? '入口で共通ログイン' : 'アプリ側') : ''),
      links(service.docs)
    );
  }

  function showVM(vm, card) {
    if (selected) selected.classList.remove('sm-selected');
    selected = card;
    highlight([vm.name]);
    detail.replaceChildren(
      el('h3', { text: vm.name }),
      el('p', { text: vm.role }),
      row('種類', kinds[vm.kind]),
      row('アドレス', vm.address),
      row('サービス', String(vm.services.length)),
      links(vm.docs)
    );
  }

  data.vms.forEach(function (vm) {
    var head = el('button', { type: 'button', class: 'sm-vm' }, [
      el('strong', { text: vm.name }), el('span', { text: vm.role })]);
    var list = el('div', { class: 'sm-services' });
    var card = el('section', { class: 'sm-card sm-' + vm.kind }, [head, list]);
    cards[vm.name] = card;
    head.addEventListener('click', function () { showVM(vm, card); });
    vm.services.forEach(function (service) {
      var chip = el('button', { type: 'button', class: 'sm-chip' + (service.url ? ' sm-web' : ''), text: service.name });
      chip.addEventListener('click', function () { showService(vm, service, chip); });
      list.appendChild(chip);
      chips.push({ chip: chip, card: card, text: (service.name + ' ' + service.description + ' ' + vm.name + ' ' + vm.role).toLowerCase() });
    });
    grid.appendChild(card);
  });

  search.addEventListener('input', function () {
    var query = search.value.trim().toLowerCase();
    var shown = {};
    chips.forEach(function (item) {
      var match = !query || item.text.indexOf(query) >= 0;
      item.chip.hidden = !match;
      if (match) shown[item.card.querySelector('strong').textContent] = true;
    });
    Object.keys(cards).forEach(function (name) {
      cards[name].hidden = !!query && !shown[name] && name.toLowerCase().indexOf(query) < 0;
    });
  });

  detail.appendChild(el('p', { class: 'sm-empty', text: 'VM かサービスを選択' }));
})();
