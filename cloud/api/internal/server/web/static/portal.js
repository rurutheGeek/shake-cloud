'use strict';
// The self-service portal. It uses the same JSON API as Terraform and the CLI,
// authenticated by the session cookie. Unsaved drafts live only in this page.
(() => {
  const $ = (id) => document.getElementById(id);
  if (!$('keys')) return; // logged out

  const { onAction, showError, announce, fieldError, blockForm, confirmAction,
    replaceOptions, emptyRow, tableRows, copyText } = window.PortalUI;
  let sessionExpired = false;
  let effectiveLimits = null;
  let maxImageGiB = 0;
  const readiness = { images: false, isos: false, keys: false, groups: false, limits: false };

  const when = (value) => (value ? new Date(value).toLocaleString('ja-JP') : '—');
  const cell = (text) => {
    const td = document.createElement('td');
    td.textContent = text;
    return td;
  };

  const reads = new Map();
  function responseError(status, data, requestID, mutation = false) {
    const messages = {
      400: '入力内容を確認してください。詳しい理由はエラーの詳細で確認できます。',
      401: 'ログインの有効期限が切れました。入力を確認してから再ログインしてください。',
      403: 'この操作を行う権限がありません。所有者とログイン中のアカウントを確認してください。',
      404: '対象が見つかりません。表示を更新し、対象を選び直してください。',
      409: '現在の状態では操作できません。表示を更新し、容量や対象の状態を確認してください。',
      413: 'ファイルまたは送信内容が上限を超えています。大きさを確認してください。',
      429: '操作が集中しています。少し待ってからやり直してください。',
    };
    const error = new Error(messages[status] || (mutation
      ? '操作結果を確認できませんでした。再送信する前に、一覧と操作履歴を確認してください。'
      : '情報を取得できませんでした。しばらく待って表示を更新してください。'));
    error.status = status;
    error.uncertain = mutation && status >= 500;
    error.detail = data?.error?.message ? `${data.error.message}（${data.error.code || status}）` : `HTTP ${status}`;
    error.requestID = data?.request_id || requestID;
    if (status === 401) {
      sessionExpired = true;
      $('session-expired').hidden = false;
    }
    return error;
  }

  function api(method, path, body) {
    if (method === 'GET' && reads.has(path)) return reads.get(path);
    const request = (async () => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), method === 'GET' ? 20000 : 60000);
      const init = { method, credentials: 'same-origin', headers: {}, signal: controller.signal };
      if (body !== undefined) {
        init.headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(body);
      }
      try {
        const response = await fetch(path, init);
        if (response.status === 204) return null;
        let data = null;
        try { data = await response.json(); } catch (_) { /* HTML errors are handled below. */ }
        if (!response.ok) throw responseError(response.status, data, response.headers.get('X-Request-ID'), method !== 'GET');
        if (!data) {
          const error = new Error('サーバーの応答を読み取れませんでした。操作結果を一覧で確認してください。');
          error.uncertain = method !== 'GET';
          throw error;
        }
        return data;
      } catch (error) {
        if (error instanceof TypeError || error.name === 'AbortError') {
          const failure = new Error(method === 'GET'
            ? '通信できませんでした。接続を確認し、表示を更新してください。'
            : '通信が途切れ、操作結果が不明です。再送信する前に一覧と履歴を確認してください。');
          failure.uncertain = method !== 'GET';
          throw failure;
        }
        throw error;
      } finally {
        clearTimeout(timeout);
      }
    })();
    if (method !== 'GET') return request;
    reads.set(path, request);
    request.finally(() => { if (reads.get(path) === request) reads.delete(path); }).catch(() => {});
    return request;
  }

  function listStatus(id, message, failed = false) {
    let element = $(id + '-status');
    if (!element) {
      const target = $(id);
      if (!target) return;
      element = document.createElement('p');
      element.id = id + '-status';
      element.setAttribute('role', 'status');
      (target.closest('.scroll') || target).before(element);
    }
    element.className = failed ? 'error' : 'muted';
    element.textContent = message;
  }

  function loadProblem(id, error) {
    listStatus(id, `${error.message} 最後に取得した表示と入力を保持しています。`, true);
  }

  function instanceSource() {
    const select = $('instance-source');
    return select ? select.value : 'image';
  }

  function updateReadiness() {
    const fromISO = instanceSource() === 'iso';
    const sourceReady = fromISO ? readiness.isos : readiness.images;
    const ready = sourceReady && readiness.keys && readiness.groups && readiness.limits;
    blockForm($('create-instance'), !ready);
    $('create-instance-readiness').textContent = ready
      ? '作成内容を確認してから送信します。'
      : fromISO
        ? '作成に必要なISO・SSH鍵・グループ・上限を取得できていません。「表示を更新」で再取得してください。'
        : '作成に必要なイメージ・SSH鍵・グループ・上限を取得できていません。「表示を更新」で再取得してください。';
    blockForm($('create-volume'), !readiness.limits);
    blockForm($('upload-image'), !readiness.limits);
    blockForm($('upload-iso'), !readiness.limits);
  }

  function resourceDescription(resource, kind = 'インスタンス') {
    const label = resource.volume_id
      ? (VOLUME_STATE_LABELS[resource.state] || resource.state)
      : stateLabel(resource.state);
    return `${kind}: ${resource.tags?.Name || resource.name || '名前なし'}\nID: ${resource.instance_id || resource.volume_id || resource.image_id}\n所有者: ${resource.owner_username || resource.account_id}\n状態: ${label}`;
  }

  async function loadKeys() {
    const { access_keys: keys } = await api('GET', '/v1/access-keys');
    const rows = keys.map((key) => {
      const row = document.createElement('tr');
      row.append(
        cell(key.access_key_id),
        cell(key.description || '—'),
        cell(key.status),
        cell(when(key.create_date)),
        cell(key.expire_date ? when(key.expire_date) : '無期限'),
        cell(when(key.last_used_date)),
      );
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = '無効化';
      button.disabled = key.status !== 'Active';
      button.className = 'danger';
      onAction(button, 'click', async (event, scope) => {
        if (!await confirmAction({ message: `キー ${key.access_key_id} を削除します。このキーを使っている Terraform や CLI は動かなくなります。`, danger: true })) return;
        try {
          $('error').hidden = true;
          await api('DELETE', `/v1/access-keys/${encodeURIComponent(key.access_key_id)}`);
          await loadKeys();
          announce('アクセスキーを無効化しました。', scope);
        } catch (error) {
          showError(error, scope);
        }
      });
      const action = document.createElement('td');
      action.append(button);
      row.append(action);
      return row;
    });
    tableRows($('keys'), rows, 'アクセスキーはありません。上のフォームから発行できます。');
    listStatus('keys', `登録 ${keys.length}件`);
  }

  // The audit API filters by event name, account and key, and pages with
  // next_token. The details stay collapsed so the table keeps its shape: the
  // request ID and resource ID are what make a failed operation traceable.
  let eventNextToken = null;

  function eventRow(event) {
    const row = document.createElement('tr');
    const detailCell = document.createElement('td');
    const target = document.createElement('span');
    target.className = 'muted small';
    target.textContent = event.resource_id || '—';
    const details = document.createElement('details');
    const title = document.createElement('summary');
    title.textContent = '詳細';
    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify({
      request_id: event.request_id,
      resource_id: event.resource_id,
      user_agent: event.user_agent,
      detail: event.detail,
    }, null, 2);
    details.append(title, pre);
    detailCell.append(target, details);
    row.append(
      cell(when(event.event_time)),
      cell(event.event_name),
      cell(event.error_code || '成功'),
      cell(event.account_id || '—'),
      cell(event.access_key_id || '—'),
      cell(event.source_ip_address || '—'),
      detailCell,
    );
    return row;
  }

  function eventQuery(nextToken) {
    const params = new URLSearchParams({ max_results: '20' });
    const filters = $('event-filters');
    if (filters) {
      const data = new FormData(filters);
      for (const name of ['event_name', 'account_id', 'access_key_id']) {
        const value = String(data.get(name) || '').trim();
        if (value) params.set(name, value);
      }
    }
    if (nextToken) params.set('next_token', nextToken);
    return `/v1/audit-events?${params.toString()}`;
  }

  async function loadEvents({ append = false } = {}) {
    const body = $('events');
    try {
      const { events, next_token: nextToken } = await api('GET', eventQuery(append ? eventNextToken : null));
      eventNextToken = nextToken || null;
      if (append) body.append(...events.map(eventRow));
      else body.replaceChildren(...(events.length ? events.map(eventRow) : [emptyRow(7, '条件に一致する操作履歴はありません。')]));
      $('more-events').hidden = !eventNextToken;
      listStatus('events', `${append ? body.querySelectorAll('tr').length : events.length}件 · 最終更新 ${when(new Date())}`);
    } catch (error) {
      if (!append) body.replaceChildren(note(error.message));
      listStatus('events', `${error.message} 最後に取得した内容を保持しています。`, true);
    }
  }

  onAction($('event-filters'), 'submit', async () => {
    delete $('event-filters').dataset.dirty;
    await loadEvents();
  });
  onAction($('clear-event-filters'), 'click', async () => {
    $('event-filters').reset();
    await loadEvents();
  });
  onAction($('more-events'), 'click', async () => { await loadEvents({ append: true }); });

  const mib = (value) => (value >= 1024 ? (value / 1024).toFixed(value >= 10240 ? 0 : 1) + ' GiB' : value + ' MiB');

  const note = (text) => {
    const p = document.createElement('p');
    p.className = 'muted';
    p.textContent = text;
    return p;
  };

  // A labelled bar. The width is set through the CSSOM, which the content
  // security policy allows; a style attribute in the markup would not be.
  function meter(label, text, percent) {
    const wrap = document.createElement('div');
    wrap.className = 'meter';
    const head = document.createElement('div');
    head.className = 'meter-head';
    const name = document.createElement('span');
    name.textContent = label;
    const value = document.createElement('span');
    value.className = 'muted';
    value.textContent = text;
    head.append(name, value);
    const track = document.createElement('div');
    track.className = 'track';
    const fill = document.createElement('div');
    fill.className = percent >= 90 ? 'fill hot' : 'fill';
    fill.style.width = Math.max(0, Math.min(100, percent)) + '%';
    track.append(fill);
    wrap.append(head, track);
    return wrap;
  }

  const share = (used, total) => (total > 0 ? (used * 100) / total : 0);

  // The remaining personal quota is shown apart from the host's real free
  // space: a quota limit of 0 means unlimited (not "zero left"), and the host
  // can still be full even when the account has quota left.
  function quotaTable(capacity) {
    const quota = capacity.limits && capacity.limits.account_quota;
    const usage = capacity.account;
    if (!quota || !usage) return note('個人の利用枠と使用量を取得できませんでした。');
    const table = document.createElement('table');
    const head = document.createElement('tr');
    for (const text of ['項目', '使用', '上限', '残り']) {
      const th = document.createElement('th');
      th.textContent = text;
      head.append(th);
    }
    const thead = document.createElement('thead');
    thead.append(head);
    const tbody = document.createElement('tbody');
    const add = (label, used, limit, format = String) => {
      const row = document.createElement('tr');
      row.append(
        cell(label),
        cell(format(used)),
        cell(limit > 0 ? format(limit) : '無制限'),
        cell(limit > 0 ? format(Math.max(0, limit - used)) : '—'),
      );
      tbody.append(row);
    };
    add('インスタンス', usage.instances, quota.instances);
    add('vCPU', usage.vcpus, quota.vcpus);
    add('メモリ', usage.memory_mib, quota.memory_mib, mib);
    add('ルートディスク', usage.root_disk_gib, quota.root_disk_gib, (value) => value + ' GiB');
    add('ボリューム数', usage.volumes, quota.volumes);
    add('ボリューム容量', usage.volume_gib, quota.volume_gib, (value) => value + ' GiB');
    table.append(thead, tbody);
    const scroll = document.createElement('div');
    scroll.className = 'scroll';
    scroll.append(table);
    return scroll;
  }

  let capacityLoaded = false;

  async function loadCapacity() {
    try {
      const capacity = await api('GET', '/v1/capacity');
      const node = capacity.node;
      const parts = [
        meter(`CPU ${node.cpu_cores}コア / ${node.cpu_threads}スレッド`,
          `使用 ${node.cpu_usage_percent}%${node.cpu_model ? ' ・ ' + node.cpu_model : ''}`, node.cpu_usage_percent),
        meter('ホストのメモリ（実際の使用）',
          `${mib(node.memory_used_mib)} / ${mib(node.memory_total_mib)} ・ 空き ${mib(node.memory_available_mib)}`,
          share(node.memory_used_mib, node.memory_total_mib)),
      ];
      const budget = capacity.limits.capacity.memory_budget_mib;
      parts.push(meter('クラウドが配ったメモリ（上限の合計）',
        budget ? `${mib(capacity.cloud.memory_mib)} / ${mib(budget)}` : `${mib(capacity.cloud.memory_mib)} ・ 枠は無制限`,
        share(capacity.cloud.memory_mib, budget)));
      for (const store of capacity.storage) {
        const limit = store.max_used_percent ? ` ・ 上限 ${store.max_used_percent}%` : '';
        parts.push(meter(`ストレージ ${store.name}`,
          `使用 ${store.used_percent}% ・ 空き ${mib(store.avail_mib)}${limit}`, store.used_percent));
      }
      parts.push(note(`クラウド全体: ${capacity.cloud.instances}台 ・ ${capacity.cloud.vcpus} vCPU`
        + ` ・ ディスク ${capacity.cloud.root_disk_gib} GiB`
        + ` ・ ボリューム ${capacity.cloud.volumes}個 / ${capacity.cloud.volume_gib} GiB`));
      parts.push(note(`あなたの利用: ${capacity.account.instances}台 ・ ${capacity.account.vcpus} vCPU`
        + ` ・ メモリ ${mib(capacity.account.memory_mib)} ・ ディスク ${capacity.account.root_disk_gib} GiB`
        + ` ・ ボリューム ${capacity.account.volumes}個 / ${capacity.account.volume_gib} GiB`));
      $('capacity').replaceChildren(...parts);
      $('quota-summary').replaceChildren(quotaTable(capacity));
      capacityLoaded = true;
      listStatus('capacity', `最終更新 ${when(new Date())}`);

      if (capacity.accounts) {
        $('account-usage').replaceChildren(...capacity.accounts.map((entry) => {
          const row = document.createElement('tr');
          row.append(cell(entry.account_id), cell(entry.username), cell(entry.instances),
            cell(entry.vcpus), cell(mib(entry.memory_mib)), cell(entry.root_disk_gib + ' GiB'),
            cell(entry.volumes), cell(entry.volume_gib + ' GiB'));
          return row;
        }));
        $('capacity-accounts').hidden = capacity.accounts.length === 0;
      }
    } catch (error) {
      if (!capacityLoaded) {
        $('capacity').replaceChildren(note(error.message));
        $('quota-summary').replaceChildren(note('利用枠を取得できませんでした。'));
      }
      listStatus('capacity', `${error.message} 最後に取得した内容を表示しています。`, true);
    }
  }

  const STATE_LABELS = {
    pending: '起動準備中',
    running: '稼働中',
    stopping: '停止処理中',
    stopped: '停止中',
    'shutting-down': '削除処理中',
    terminated: '削除済み',
  };
  const TRANSIENT_STATES = new Set(['pending', 'stopping', 'shutting-down']);
  const stateLabel = (state) => STATE_LABELS[state] || state;

  function option(value, text) {
    const el = document.createElement('option');
    el.value = value;
    el.textContent = text;
    return el;
  }

  // Renders a single row of the images table. An image may be deleted by its
  // owner or by an admin; the deployment's shared (public) images cannot be
  // deleted from here at all.
  function imageRow(image, viewerAccountId, isAdmin) {
    const row = document.createElement('tr');
    row.dataset.resource = 'image:' + image.image_id;
    const owner = image.public ? '共有' : (image.owner_username || image.account_id);
    const nameCell = document.createElement('td');
    nameCell.append(image.name);
    if (image.os === 'windows') {
      const badge = document.createElement('span');
      badge.className = 'badge';
      badge.textContent = 'Windows 11';
      nameCell.append(badge);
    }
    row.append(
      nameCell,
      cell(owner),
      cell(image.format || '—'),
      cell(image.size_mib ? mib(image.size_mib) : '—'),
      cell(when(image.created_at)),
    );
    const actions = document.createElement('td');
    if (!image.public && (image.account_id === viewerAccountId || isAdmin)) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = '削除';
      button.className = 'danger';
      onAction(button, 'click', async (event, scope) => {
        if (!await confirmAction({ message: `イメージ「${image.name}」を削除します。すでにこのイメージから作ったVMには影響しません（ディスクはコピーされています）。`, danger: true })) return;
        try {
          $('error').hidden = true;
          await api('DELETE', `/v1/images/${encodeURIComponent(image.image_id)}`);
          await Promise.all([loadImages(), loadCapacity()]);
        } catch (error) {
          showError(error, scope);
        }
      });
      actions.append(button);
    }
    row.append(actions);
    return row;
  }

  // The image declares its guest OS, so the create form can adapt without a
  // separate choice: a Windows image gets the Windows hardware and no SSH key.
  const imageOS = new Map();
  const isWindowsImage = () => imageOS.get(document.querySelector('#create-instance select[name="image_id"]').value) === 'windows';

  function updateGuestOS() {
    const windows = instanceSource() === 'image' && isWindowsImage();
    $('key-name-field').hidden = windows || instanceSource() === 'iso';
    $('image-os-note').hidden = !windows;
    $('image-os-note').textContent = windows
      ? 'Windows 11 のイメージです。SSH鍵は使われません。初回起動後、コンソールでセットアップしてください（ネットワークとホスト名は自動設定されます）。'
      : '';
    if (windows) document.querySelector('#create-instance select[name="key_name"]').value = '';
  }

  // Switching between launching from an image and installing from ISO media.
  // The form keeps both selects; only the relevant one is shown and required.
  function updateSource() {
    const fromISO = instanceSource() === 'iso';
    $('image-field').hidden = fromISO;
    $('install-iso-field').hidden = !fromISO;
    $('driver-iso-field').hidden = !fromISO;
    $('iso-note').hidden = !fromISO;
    const image = document.querySelector('#create-instance select[name="image_id"]');
    if (image) image.disabled = fromISO;
    const install = document.querySelector('#create-instance select[name="install_iso_id"]');
    if (install) install.required = fromISO;
    updateGuestOS();
    updateReadiness();
  }

  async function loadImages() {
    const select = document.querySelector('#create-instance select[name="image_id"]');
    const wrap = $('images-wrap');
    const viewerAccountId = wrap.dataset.accountId;
    const isAdmin = wrap.dataset.isAdmin === 'true';
    try {
      const { images } = await api('GET', '/v1/images');
      imageOS.clear();
      for (const image of images) if (image.os) imageOS.set(image.image_id, image.os);
      replaceOptions(select, [option('', 'イメージを選んでください'),
        ...images.map((image) => option(image.image_id, image.os === 'windows' ? `${image.name}（Windows 11）` : image.name))]);
      updateGuestOS();
      readiness.images = images.length > 0;
      updateReadiness();
      tableRows($('images'), images.map((image) => imageRow(image, viewerAccountId, isAdmin)), 'イメージがありません。上のフォームからアップロードしてください。');
      listStatus('images', `登録 ${images.length}件`);
    } catch (error) {
      readiness.images = false;
      updateReadiness();
      loadProblem('images', error);
    }
  }

  // ISO installation media. An ISO is attached as a CD-ROM, never as the root
  // disk, so it is listed and used separately from images.
  function isoRow(iso, viewerAccountId, isAdmin) {
    const row = document.createElement('tr');
    row.dataset.resource = 'iso:' + iso.iso_id;
    const osCell = document.createElement('td');
    osCell.textContent = iso.os === 'windows' ? 'Windows 11' : 'Linux';
    const actions = document.createElement('td');
    if (!iso.public && (iso.account_id === viewerAccountId || isAdmin)) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = '削除';
      button.className = 'danger';
      onAction(button, 'click', async (event, scope) => {
        if (!await confirmAction({ title: 'ISOを削除',
          message: `ISO「${iso.name}」を削除します。これでインストール中のVMがあると失敗します。`,
          confirmLabel: 'このISOを削除', danger: true })) return;
        try {
          $('error').hidden = true;
          await api('DELETE', `/v1/isos/${encodeURIComponent(iso.iso_id)}`);
          await loadISOs();
        } catch (error) {
          showError(error, scope);
        }
      });
      actions.append(button);
    }
    row.append(cell(iso.name), osCell, cell(iso.public ? '共有' : (iso.owner_username || iso.account_id || '—')),
      cell(iso.size_mib ? mib(iso.size_mib) : '—'), cell(when(iso.created_at)), actions);
    return row;
  }

  async function loadISOs() {
    const install = document.querySelector('#create-instance select[name="install_iso_id"]');
    const driver = document.querySelector('#create-instance select[name="driver_iso_id"]');
    const wrap = $('images-wrap');
    const viewerAccountId = wrap.dataset.accountId;
    const isAdmin = wrap.dataset.isAdmin === 'true';
    try {
      const { isos } = await api('GET', '/v1/isos');
      const labelled = (iso) => option(iso.iso_id, iso.os === 'windows' ? `${iso.name}（Windows 11）` : iso.name);
      replaceOptions(install, [option('', 'インストールISOを選んでください'), ...isos.map(labelled)]);
      const placeholder = driver.querySelector('option[value=""]') || option('', '使わない');
      replaceOptions(driver, [placeholder, ...isos.map(labelled)]);
      readiness.isos = isos.length > 0;
      updateReadiness();
      tableRows($('isos'), isos.map((iso) => isoRow(iso, viewerAccountId, isAdmin)), 'ISOがありません。上のフォームからアップロードしてください。');
      listStatus('isos', `登録 ${isos.length}件`);
    } catch (error) {
      readiness.isos = false;
      updateReadiness();
      loadProblem('isos', error);
    }
  }

  function keyPairRow(keyPair) {
    const row = document.createElement('tr');
    row.dataset.resource = 'ssh:' + keyPair.key_name;
    row.append(cell(keyPair.key_name), cell(keyPair.fingerprint), cell(when(keyPair.created_at)));
    const actions = document.createElement('td');
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = '削除';
    button.className = 'danger';
    onAction(button, 'click', async (event, scope) => {
      if (!await confirmAction({ message: `SSH鍵「${keyPair.key_name}」を削除します。すでにこの鍵で作ったVMはそのまま使えます（鍵は作成時にVMへ書き込み済みです）。`, danger: true })) return;
      try {
        $('error').hidden = true;
        await api('DELETE', `/v1/key-pairs/${encodeURIComponent(keyPair.key_name)}`);
        await loadKeyPairs();
      } catch (error) {
        showError(error, scope);
      }
    });
    actions.append(button);
    row.append(actions);
    return row;
  }

  // Fills both the SSH鍵 table and the create-instance key select from the
  // same fetch; the select keeps its "使わない" placeholder either way.
  async function loadKeyPairs() {
    const select = document.querySelector('#create-instance select[name="key_name"]');
    const placeholder = select.querySelector('option[value=""]') || option('', '使わない');
    try {
      const { key_pairs: keyPairs } = await api('GET', '/v1/key-pairs');
      replaceOptions(select, [placeholder, ...keyPairs.map((keyPair) => option(keyPair.key_name, keyPair.key_name))]);
      readiness.keys = true;
      updateReadiness();
      tableRows($('key-pairs'), keyPairs.map(keyPairRow), 'SSH鍵はありません。公開鍵を登録するとVM作成時に選択できます。');
      listStatus('key-pairs', `登録 ${keyPairs.length}件`);
    } catch (error) {
      readiness.keys = false;
      updateReadiness();
      loadProblem('key-pairs', error);
    }
  }

  // Filled in by loadInstanceTypes and read by the preset <select>'s change
  // handler, so picking a preset can fill in the vCPU/memory/floor inputs.
  let presetTypes = new Map();

  // Filled in by loadSecurityGroups and read wherever an instance's own
  // groups (or, for an admin, another account's groups) need listing without
  // an extra round trip: the create-instance checklist and the instance
  // table's "変更" edit row.
  let lastSecurityGroups = [];

  async function loadInstanceTypes() {
    const select = document.querySelector('#create-instance select[name="preset"]');
    try {
      const { instance_types: types } = await api('GET', '/v1/instance-types');
      presetTypes = new Map(types.map((type) => [type.instance_type, type]));
      for (const type of types) {
        const option = document.createElement('option');
        option.value = type.instance_type;
        option.textContent = `${type.instance_type} — ${type.vcpus} vCPU / ${type.memory_mib} MiB`;
        select.append(option);
      }
    } catch (error) {
      $('instance-preset-status').textContent = '雛形を取得できませんでした。構成を直接入力できます。';
    }
  }

  function powerButton(label, path, enabled) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.disabled = !enabled;
    onAction(button, 'click', async (event, scope) => {
      try {
        $('error').hidden = true;
        await api('POST', path);
        await Promise.all([loadInstances(), loadCapacity()]);
      } catch (error) {
        showError(error, scope);
      }
    });
    return button;
  }

  // Opens the browser VNC console in a new tab. The tab is opened
  // synchronously inside the click handler (as about:blank) because the API
  // call that follows requires an await, and browsers may refuse to honor a
  // window.open() that happens after one — it would then look like an
  // unrequested popup instead of a direct result of the click. The tab's
  // location is filled in once the one-time console URL comes back, or the
  // tab is closed again if the request fails.
  function consoleButton(instance) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = 'コンソール';
    button.disabled = instance.state !== 'running';
    onAction(button, 'click', async (event, scope) => {
      const win = window.open('about:blank', '_blank');
      try {
        $('error').hidden = true;
        const id = encodeURIComponent(instance.instance_id);
        const data = await api('POST', `/v1/instances/${id}/console`);
        const url = new URL(data.console.url, location.origin);
        if (url.origin !== location.origin || !url.pathname.startsWith('/console/')) {
          throw new Error('コンソールの接続先を確認できませんでした。');
        }
        if (win) {
          win.opener = null;
          win.location.href = url.href;
        } else {
          announce('ポップアップがブロックされました。下のリンクから5分以内に開いてください。', scope);
          const link = document.createElement('a');
          link.href = url.href;
          link.target = '_blank';
          link.rel = 'noopener';
          link.textContent = `${instance.tags?.Name || instance.instance_id} のコンソールを開く`;
          const container = $('instances-view');
          container.querySelector('.console-fallback')?.remove();
          link.className = 'console-fallback button';
          container.prepend(link);
          link.focus();
          setTimeout(() => link.remove(), 5 * 60 * 1000);
        }
      } catch (error) {
        if (win) win.close();
        showError(error, scope);
      }
    });
    return button;
  }

  function deleteInstanceButton(instance) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = '削除';
    button.disabled = instance.state === 'terminated';
    button.className = 'danger';
    onAction(button, 'click', async (event, scope) => {
      if (!await confirmAction({ title: 'インスタンスを削除',
        message: resourceDescription(instance) + '\n\nこのVMとルートディスクを削除します。追加ボリュームは切り離して保持します。この操作は取り消せません。',
        confirmLabel: 'このインスタンスを削除', danger: true })) return;
      try {
        $('error').hidden = true;
        await api('DELETE', `/v1/instances/${encodeURIComponent(instance.instance_id)}`);
        announce(`${instance.tags?.Name || instance.instance_id} の削除を受け付けました。`, scope);
        await Promise.all([loadInstances(), loadCapacity()]);
      } catch (error) {
        showError(error, scope);
      }
    });
    return button;
  }

  function numberField(labelText, name, value, min) {
    const label = document.createElement('label');
    label.append(labelText + ' ');
    const input = document.createElement('input');
    input.type = 'number';
    input.name = name;
    input.min = String(min);
    input.step = '1';
    input.value = value;
    label.append(input);
    return { label, input };
  }

  async function dismissEditor(editRow, source) {
    if (editRow.querySelector('form[data-dirty="true"]') && !await confirmAction({
      title: '編集中の内容を閉じる', message: '保存していない変更を破棄します。', confirmLabel: '変更を破棄' })) return false;
    editRow.remove();
    renderInstances();
    source?.focus();
    return true;
  }

  function mountEditor(row, instance, form, source) {
    const editRow = document.createElement('tr');
    editRow.className = 'edit-row';
    form.dataset.resource = instance.instance_id;
    const td = document.createElement('td');
    td.colSpan = 9;
    td.append(form);
    editRow.append(td);
    row.after(editRow);
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.textContent = '閉じる';
    onAction(cancel, 'click', async () => { await dismissEditor(editRow, source); });
    form.append(cancel);
    form.querySelector('input:not(:disabled), select:not(:disabled), button')?.focus();
    return editRow;
  }

  async function currentInstance(instance) {
    const { instances } = await api('GET', '/v1/instances');
    const current = instances.find((item) => item.instance_id === instance.instance_id);
    if (!current || ['terminated', 'shutting-down'].includes(current.state)) {
      throw new Error('対象は削除されたか、削除処理中です。未保存の入力は保持しています。');
    }
    return current;
  }

  async function toggleEditRow(row, instance, source) {
    const already = row.nextElementSibling;
    if (already?.classList.contains('edit-row')) { await dismissEditor(already, source); return; }
    const vcpus = numberField('vCPU', 'vcpus', instance.vcpus, 1);
    const memory = numberField('メモリ MiB', 'memory_mib', instance.memory_mib, 512);
    const memoryMin = numberField('最小メモリ MiB', 'memory_min_mib', instance.memory_min_mib || 512, 512);
    const disk = numberField('ルートディスク GiB', 'root_disk_gib', instance.root_disk_gib, instance.root_disk_gib);
    if (effectiveLimits) disk.input.max = String(effectiveLimits.root_disk_gib.max);
    for (const input of [vcpus.input, memory.input, memoryMin.input, disk.input]) input.required = true;
    const balloonLabel = document.createElement('label');
    const balloon = document.createElement('input');
    balloon.type = 'checkbox';
    balloon.checked = instance.ballooning;
    balloonLabel.append(balloon, ' バルーニングを使う');
    const stopped = instance.state === 'stopped';
    vcpus.input.disabled = memory.input.disabled = balloon.disabled = !stopped;
    const updateFloor = () => { memoryMin.input.disabled = !stopped || !balloon.checked; };
    balloon.addEventListener('change', updateFloor);
    updateFloor();
    const hint = note('vCPU・メモリは停止中だけ変更できます。ディスクは拡大のみで、縮小できません。');
    hint.classList.add('wide');
    const save = document.createElement('button');
    save.type = 'submit'; save.textContent = '変更を保存';
    const form = document.createElement('form');
    form.className = 'edit-instance';
    form.append(vcpus.label, memory.label, balloonLabel, memoryMin.label, disk.label, hint, save);
    const editRow = mountEditor(row, instance, form, source);
    onAction(form, 'submit', async (event, scope) => {
      const patch = {};
      if (stopped && Number(vcpus.input.value) !== instance.vcpus) patch.vcpus = Number(vcpus.input.value);
      if (stopped && Number(memory.input.value) !== instance.memory_mib) patch.memory_mib = Number(memory.input.value);
      if (stopped && balloon.checked !== instance.ballooning) patch.ballooning = balloon.checked;
      if (stopped && balloon.checked && Number(memoryMin.input.value) !== instance.memory_min_mib) patch.memory_min_mib = Number(memoryMin.input.value);
      if (Number(disk.input.value) !== instance.root_disk_gib) patch.root_disk_gib = Number(disk.input.value);
      if (!Object.keys(patch).length) { announce('変更はありません。', scope); return; }
      if (balloon.checked && Number(memoryMin.input.value) > Number(memory.input.value)) {
        fieldError(memoryMin.input, '最小メモリは最大メモリ以下にしてください。'); return;
      }
      const current = await currentInstance(instance);
      const fields = ['vcpus', 'memory_mib', 'memory_min_mib', 'ballooning', 'root_disk_gib'];
      if (fields.some((name) => current[name] !== instance[name])) throw new Error('別の操作で構成が変わりました。入力を控え、編集を開き直して最新の構成を確認してください。');
      if (current.state !== 'stopped' && Object.keys(patch).some((name) => name !== 'root_disk_gib')) throw new Error('VMが停止中ではありません。CPU・メモリを変更するには停止が必要です。入力は保持しています。');
      await api('PATCH', `/v1/instances/${encodeURIComponent(instance.instance_id)}`, patch);
      delete form.dataset.dirty;
      editRow.remove();
      announce(`${instance.tags?.Name || instance.instance_id} の構成を変更しました。`);
      await Promise.all([loadInstances(), loadCapacity()]);
    });
  }

  async function toggleGroupEditRow(row, instance, source) {
    const already = row.nextElementSibling;
    if (already?.classList.contains('edit-row')) { await dismissEditor(already, source); return; }
    const candidates = lastSecurityGroups.filter((group) => group.account_id === instance.account_id);
    const current = new Set((instance.security_groups || []).map((group) => group.group_id));
    const form = document.createElement('form');
    form.className = 'edit-instance';
    const checklist = document.createElement('fieldset');
    const legend = document.createElement('legend');
    legend.textContent = '適用するセキュリティグループ（1〜5個）';
    checklist.append(legend);
    const inputs = candidates.map((group) => {
      const label = document.createElement('label');
      const input = document.createElement('input');
      input.type = 'checkbox'; input.value = group.group_id; input.checked = current.has(group.group_id);
      label.append(input, group.group_name); checklist.append(label);
      return input;
    });
    const save = document.createElement('button');
    save.type = 'submit'; save.textContent = '変更内容を確認';
    form.append(checklist, save);
    const editRow = mountEditor(row, instance, form, source);
    onAction(form, 'submit', async (event, scope) => {
      const selected = inputs.filter((input) => input.checked).map((input) => input.value);
      if (selected.length < 1 || selected.length > 5) throw new Error('セキュリティグループは1〜5個選んでください。');
      const latest = await currentInstance(instance);
      const latestIDs = (latest.security_groups || []).map((group) => group.group_id).sort().join(',');
      if (latestIDs !== [...current].sort().join(',')) throw new Error('別の操作でグループが変更されました。入力を控え、編集を開き直してください。');
      const { security_groups: groups } = await api('GET', '/v1/security-groups');
      if (selected.some((id) => !groups.some((group) => group.group_id === id && group.account_id === instance.account_id))) throw new Error('選んだグループが利用できなくなりました。表示を更新して選び直してください。');
      if (!await confirmAction({ title: '通信の許可範囲を変更', confirmLabel: 'このグループを適用', message: resourceDescription(latest) + '\n\n適用するグループ: ' + selected.map((id) => groups.find((g) => g.group_id === id).group_name).join('、') + '\n接続中の通信が切れる場合があります。' })) return;
      await api('PUT', `/v1/instances/${encodeURIComponent(instance.instance_id)}/security-groups`, { security_group_ids: selected });
      delete form.dataset.dirty;
      editRow.remove();
      announce('セキュリティグループの変更を受け付けました。反映状態を確認しています。');
      await loadInstances();
    });
  }

  function instanceRow(instance, viewerAccountId, isAdmin) {
    const row = document.createElement('tr');
    row.dataset.resource = instance.instance_id;
    row.dataset.snapshot = JSON.stringify(instance);

    const nameCell = document.createElement('td');
    nameCell.append((instance.tags && instance.tags.Name) || '—');
    const identifier = document.createElement('span');
    identifier.className = 'muted small';
    identifier.textContent = instance.instance_id;
    nameCell.append(identifier);
    if (instance.adopted) {
      const badge = document.createElement('span');
      badge.className = 'badge';
      badge.textContent = '引き取り';
      nameCell.append(badge);
    }
    if (instance.state_reason) {
      const reason = document.createElement('div');
      reason.className = 'muted small';
      reason.textContent = instance.state_reason;
      nameCell.append(reason);
    }

    const stateCell = document.createElement('td');
    const state = document.createElement('span');
    state.className = `state state-${instance.state}`;
    state.textContent = stateLabel(instance.state);
    stateCell.append(state);

    const configCell = document.createElement('td');
    const typeLine = document.createElement('div');
    typeLine.textContent = instance.instance_type || 'カスタム';
    const detailLine = document.createElement('div');
    detailLine.className = 'muted small';
    detailLine.textContent = `${instance.vcpus} vCPU / ${mib(instance.memory_mib)}`
      + (instance.ballooning ? ` ・ 最小 ${mib(instance.memory_min_mib)}` : ' ・ 固定');
    configCell.append(typeLine, detailLine);

    const groupsCell = document.createElement('td');
    const groups = instance.security_groups || [];
    if (groups.length === 0) {
      const none = document.createElement('span');
      none.className = 'muted';
      none.textContent = 'なし（制限なし）';
      groupsCell.append(none);
    } else {
      groupsCell.append(groups.map((group) => group.group_name).join(', '));
    }
    if (instance.firewall_state === 'applying') {
      const applying = document.createElement('div');
      applying.className = 'muted small';
      applying.textContent = '反映中';
      groupsCell.append(applying);
    }

    row.append(
      nameCell,
      cell(instance.owner_username || instance.account_id),
      stateCell,
      cell(instance.private_ip_address || '—'),
      cell(instance.adopted ? '—（引き取り）' : (instance.image_name || instance.image_id)),
      configCell,
      cell(instance.root_disk_gib + ' GiB'),
      groupsCell,
    );

    const canAct = instance.account_id === viewerAccountId || isAdmin;
    if (canAct && instance.state !== 'terminated') {
      const changeGroups = document.createElement('button');
      changeGroups.type = 'button';
      changeGroups.textContent = '変更';
      onAction(changeGroups, 'click', async () => { await toggleGroupEditRow(row, instance, changeGroups); });
      groupsCell.append(changeGroups);
    }

    const actions = document.createElement('td');
    if (canAct) {
      const id = encodeURIComponent(instance.instance_id);
      actions.append(
        powerButton('起動', `/v1/instances/${id}/start`, instance.state === 'stopped'),
        powerButton('停止', `/v1/instances/${id}/stop`, instance.state === 'running'),
        powerButton('再起動', `/v1/instances/${id}/reboot`, instance.state === 'running'),
        consoleButton(instance),
        deleteInstanceButton(instance),
      );
    }
    if (isAdmin && !['terminated', 'shutting-down'].includes(instance.state)) {
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.textContent = '編集';
      onAction(edit, 'click', async () => { await toggleEditRow(row, instance, edit); });
      actions.append(edit);
    }
    row.append(actions);
    return row;
  }

  let lastInstances = [];
  let instancesLoaded = false;
  let instancePollTimer = null;
  let instanceFailures = 0;

  function syncResourceRows(body, rows, columns) {
    const existing = new Map([...body.querySelectorAll(':scope > tr[data-resource]')]
      .map((row) => [row.dataset.resource, row]));
    const ids = new Set(rows.map((row) => row.dataset.resource));
    for (const placeholder of body.querySelectorAll(':scope > tr:not([data-resource]):not(.edit-row)')) placeholder.remove();
    for (const next of rows) {
      const old = existing.get(next.dataset.resource);
      if (!old) { body.append(next); continue; }
      const edit = old.nextElementSibling?.classList.contains('edit-row') ? old.nextElementSibling : null;
      const protectedRow = edit || old.dataset.dirty === 'true' || old.matches('[aria-busy="true"]') || old.querySelector('[aria-busy="true"]');
      old.hidden = next.hidden;
      if (edit) edit.hidden = next.hidden;
      if (old.dataset.snapshot === next.dataset.snapshot) continue;
      if (protectedRow) {
        // Preserve the controls and closures' baseline. The save handler checks
        // the latest resource before applying its patch.
        const indices = body.id === 'instances' ? [2, 3, 5, 6] : [3, 4, 5, 6];
        for (const index of indices) old.cells[index].replaceChildren(...next.cells[index].childNodes);
        let warning = old.cells[0].querySelector('.stale-warning');
        if (!warning) {
          warning = document.createElement('span');
          warning.className = 'stale-warning small';
          warning.textContent = '状態が更新されました。入力は保持しています。';
          old.cells[0].append(warning);
        }
        continue;
      }
      const active = old.contains(document.activeElement) ? document.activeElement.textContent : null;
      old.replaceWith(next);
      if (active) [...next.querySelectorAll('button:not(:disabled)')].find((button) => button.textContent === active)?.focus();
    }
    for (const [id, old] of existing) {
      if (ids.has(id) || !old.isConnected) continue;
      const edit = old.nextElementSibling?.classList.contains('edit-row') ? old.nextElementSibling : null;
      if (edit || old.dataset.dirty === 'true' || old.matches('[aria-busy="true"]')) {
        old.cells[0].textContent = `${id}：一覧からなくなりました。未保存の入力を保持しています。`;
        if (edit) blockForm(edit.querySelector('form'), true);
      } else old.remove();
    }
    if (!body.children.length) body.append(emptyRow(columns, 'まだ登録されていません。作成するとここに表示されます。'));
  }

  function renderInstances() {
    if (!instancesLoaded) return;
    const wrap = $('instances-wrap');
    const search = $('instance-search').value.trim().toLocaleLowerCase();
    const owner = $('instance-owner').value;
    const state = $('instance-state').value;
    let visible = 0;
    const rows = lastInstances.map((instance) => {
      const row = instanceRow(instance, wrap.dataset.accountId, wrap.dataset.isAdmin === 'true');
      const text = [instance.tags?.Name, instance.instance_id, instance.private_ip_address, instance.owner_username, instance.account_id].join(' ').toLocaleLowerCase();
      row.hidden = !!((search && !text.includes(search)) || (owner === 'mine' && instance.account_id !== wrap.dataset.accountId) || (state && state !== instance.state));
      if (!row.hidden) visible++;
      return row;
    });
    syncResourceRows($('instances'), rows, 9);
    let empty = $('instance-filter-empty');
    if (!empty) {
      empty = document.createElement('p'); empty.id = 'instance-filter-empty';
      $('instances-wrap').after(empty);
    }
    empty.textContent = '条件に一致するインスタンスはありません。検索条件を変更してください。';
    empty.hidden = visible > 0 || lastInstances.length === 0;
    $('operation-summary').textContent = `インスタンス ${lastInstances.length}台 · 処理中 ${lastInstances.filter((i) => TRANSIENT_STATES.has(i.state) || i.firewall_state === 'applying').length}台 · 状態の説明あり ${lastInstances.filter((i) => i.state_reason).length}台`;
  }

  for (const id of ['instance-search', 'instance-owner', 'instance-state']) {
    $(id).addEventListener('input', renderInstances);
    $(id).addEventListener('change', renderInstances);
  }

  function scheduleInstancePoll(delay = 30000) {
    clearTimeout(instancePollTimer);
    if (!sessionExpired) instancePollTimer = setTimeout(loadInstances, delay);
  }

  async function loadInstances() {
    try {
      const { instances } = await api('GET', '/v1/instances');
      lastInstances = instances;
      instancesLoaded = true;
      instanceFailures = 0;
      renderInstances();
      listStatus('instances', `${instances.length}台 · 最終更新 ${when(new Date())}`);
      const busy = instances.some((instance) => TRANSIENT_STATES.has(instance.state) || instance.firewall_state === 'applying');
      scheduleInstancePoll(busy && !document.hidden ? 5000 : 30000);
    } catch (error) {
      loadProblem('instances', error);
      scheduleInstancePoll(Math.min(60000, 5000 * (2 ** Math.min(++instanceFailures, 4))));
    }
  }

  const createInstanceForm = $('create-instance');
  createInstanceForm.querySelector('select[name="image_id"]').addEventListener('change', updateGuestOS);
  $('instance-source').addEventListener('change', () => { updateSource(); });
  updateSource();
  createInstanceForm.querySelector('select[name="preset"]').addEventListener('change', (event) => {
    const preset = presetTypes.get(event.target.value);
    if (!preset) { $('instance-preset-status').textContent = 'カスタム構成です。'; return; }
    createInstanceForm.querySelector('input[name="vcpus"]').value = preset.vcpus;
    createInstanceForm.querySelector('input[name="memory_mib"]').value = preset.memory_mib;
    createInstanceForm.querySelector('input[name="memory_min_mib"]').value = preset.memory_min_mib;
    $('instance-preset-status').textContent = `${preset.instance_type} の値を入力しました。数値は自由に変更できます。`;
  });
  createInstanceForm.querySelector('input[name="ballooning"]').addEventListener('change', (event) => {
    createInstanceForm.querySelector('input[name="memory_min_mib"]').disabled = !event.target.checked;
  });
  for (const input of createInstanceForm.querySelectorAll('input[type=number], input[name=ballooning]')) {
    input.addEventListener('input', () => {
      createInstanceForm.elements.preset.value = '';
      $('instance-preset-status').textContent = 'カスタム構成です。入力した数値で作成します。';
    });
  }
  // Reuse a token for the same logical request, even if an earlier response
  // was lost. Hashes avoid retaining user-data in a second draft object.
  const launchTokens = new Map();
  let uncertainLaunch = false;
  onAction(createInstanceForm, 'submit', async (submit, scope) => {
    submit.preventDefault();
    const fromISO = instanceSource() === 'iso';
    const windows = !fromISO && isWindowsImage();
    const data = new FormData(createInstanceForm);
    const vcpus = data.get('vcpus');
    const memoryMib = data.get('memory_mib');
    const body = {
      ballooning: createInstanceForm.querySelector('input[name="ballooning"]').checked,
    };
    if (fromISO) {
      body.install_iso_id = data.get('install_iso_id');
      const driverISO = data.get('driver_iso_id');
      if (driverISO) body.driver_iso_id = driverISO;
    } else {
      body.image_id = data.get('image_id');
    }
    if (vcpus) body.vcpus = Number(vcpus);
    if (memoryMib) body.memory_mib = Number(memoryMib);
    const memoryMinMib = data.get('memory_min_mib');
    if (memoryMinMib) body.memory_min_mib = Number(memoryMinMib);
    const rootDiskGib = data.get('root_disk_gib');
    if (rootDiskGib) body.root_disk_gib = Number(rootDiskGib);
    const userData = data.get('user_data');
    if (userData) body.user_data = userData;
    // A Windows image and any ISO install are configured at the console, not
    // by an SSH key.
    const keyName = (windows || fromISO) ? '' : data.get('key_name');
    if (keyName) body.key_name = keyName;
    const name = data.get('name');
    if (name) body.tags = { Name: name };
    // Omitted entirely (rather than sent empty) when nothing is checked, so
    // the API falls back to the account's default group.
    const groupIds = data.getAll('security_group_ids');
    if (groupIds.length > 0) body.security_group_ids = groupIds;
    const sourceReady = fromISO ? readiness.isos : readiness.images;
    if (!sourceReady || !readiness.keys || !readiness.groups || !readiness.limits) {
      throw new Error('作成に必要な情報を再取得してください。');
    }
    if (fromISO && !body.install_iso_id) throw new Error('インストールISOを選んでください。');
    if (body.ballooning && body.memory_min_mib > body.memory_mib) {
      fieldError(createInstanceForm.elements.memory_min_mib, '最小メモリは最大メモリ以下にしてください。');
      return;
    }
    if (body.root_disk_gib && effectiveLimits) {
      const disk = effectiveLimits.root_disk_gib;
      if (body.root_disk_gib < disk.min || body.root_disk_gib > disk.max) {
        fieldError(createInstanceForm.elements.root_disk_gib, `ルートディスクは ${disk.min}〜${disk.max} GiB にしてください。`);
        return;
      }
    }
    if (groupIds.length > 5) throw new Error('セキュリティグループは5個以内で選んでください。');
    const missingGroup = [...createInstanceForm.querySelectorAll('[name="security_group_ids"]:checked')].some((input) => input.dataset.missing === 'true');
    if (missingGroup) throw new Error('選択したグループが利用できません。グループを選び直してください。');
    const bytes = new TextEncoder().encode(JSON.stringify(body));
    const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map((byte) => byte.toString(16).padStart(2, '0')).join('');
    if (uncertainLaunch && !launchTokens.has(digest)) {
      if (!await confirmAction({ title: '前の作成結果が不明です', message: '前の要求でVMが作成されている可能性があります。一覧と履歴を確認してから、変更した構成で別のVMを作成してください。', confirmLabel: '別の作成として続ける' })) return;
    }
    const sourceName = fromISO
      ? `ISO: ${createInstanceForm.elements.install_iso_id.selectedOptions[0]?.textContent}\n方式: ISOからインストール（コンソールでセットアップ）`
      : `イメージ: ${createInstanceForm.elements.image_id.selectedOptions[0]?.textContent}`;
    const selectedGroups = groupIds.length ? groupIds.map((id) => lastSecurityGroups.find((g) => g.group_id === id)?.group_name || id).join('、') : '既定グループ（全通信を許可）';
    if (!await confirmAction({ title: 'インスタンスの作成内容', confirmLabel: 'この構成で作成',
      message: `名前: ${name || '未指定'}\nゲストOS: ${windows ? 'Windows 11' : (fromISO ? 'ISOのOS' : 'Linux')}\n${sourceName}\nvCPU: ${body.vcpus}\nメモリ: ${body.memory_mib} MiB\nルートディスク: ${body.root_disk_gib || effectiveLimits.root_disk_gib.default} GiB\n${windows ? '初回起動後のセットアップ: コンソールから' : (fromISO ? 'SSH鍵: 使いません' : `SSH鍵: ${keyName || '使わない'}`)}\n通信: ${selectedGroups}\n初回起動時の設定: ${userData ? 'あり' : 'なし'}` })) return;
    if (!launchTokens.has(digest)) launchTokens.set(digest, crypto.randomUUID());
    body.client_token = launchTokens.get(digest);
    try {
      const result = await api('POST', '/v1/instances', body);
      launchTokens.delete(digest);
      uncertainLaunch = false;
      createInstanceForm.reset();
      createInstanceForm.querySelector('input[name="memory_min_mib"]').disabled = false;
      updateSource();
      announce(`作成を受け付けました。${result.instance.instance_id} の状態を一覧で確認できます。`, scope);
      await Promise.all([loadInstances(), loadCapacity()]);
      location.hash = 'instances-view';
    } catch (error) {
      uncertainLaunch = uncertainLaunch || !!error.uncertain;
      showError(error, scope);
    }

  });

  const adoptForm = $('adopt-instance-form');
  if (adoptForm) {
    onAction(adoptForm, 'submit', async (submit, scope) => {
      submit.preventDefault();
      const data = new FormData(adoptForm);
      const body = { vmid: Number(data.get('vmid')), account_id: data.get('account_id') };
      if (data.get('name')) body.name = data.get('name');
      if (data.get('private_ip_address')) body.private_ip_address = data.get('private_ip_address');
      const status = $('adopt-status');
      try {
        $('error').hidden = true;
        status.textContent = '引き取っています…';
        const result = await api('POST', '/v1/instances/adopt', body);
        status.textContent = `引き取りました: ${result.instance.instance_id}`;
        adoptForm.reset();
        await Promise.all([loadInstances(), loadCapacity()]);
      } catch (error) {
        status.textContent = '';
        showError(error, scope);
      }
    });
  }

  const VOLUME_STATE_LABELS = {
    creating: '作成中',
    available: '未接続',
    'in-use': '使用中',
    deleting: '削除中',
    deleted: '削除済み',
    error: 'エラー',
  };
  const VOLUME_TRANSIENT_STATES = new Set(['creating', 'deleting']);
  const ATTACHMENT_STATE_LABELS = { attaching: '接続中', attached: '接続済み', detaching: '切断中' };

  function volumeStateCell(volume) {
    const td = document.createElement('td');
    const state = document.createElement('span');
    state.className = `state state-${volume.state}`;
    state.textContent = VOLUME_STATE_LABELS[volume.state] || volume.state;
    td.append(state);
    if (volume.modification_state) {
      const mod = document.createElement('span');
      mod.className = 'muted small';
      mod.textContent = ' 拡張中';
      td.append(mod);
    }
    if (volume.state_reason) {
      const reason = document.createElement('div');
      reason.className = 'muted small';
      reason.textContent = volume.state_reason;
      td.append(reason);
    }
    return td;
  }

  // instances is the freshly-fetched instance list (loadVolumes fetches its
  // own copy, rather than relying on loadInstances' cadence, so the name shown
  // here and the attach candidates below are never a refresh cycle stale).
  function volumeAttachmentCell(volume, instances) {
    const td = document.createElement('td');
    if (!volume.attachment) {
      td.textContent = '—';
      return td;
    }
    const target = instances.find((instance) => instance.instance_id === volume.attachment.instance_id);
    const name = target ? ((target.tags && target.tags.Name) || target.instance_id) : volume.attachment.instance_id;
    const line = document.createElement('div');
    line.textContent = `${name}（${volume.attachment.device}）`;
    const state = document.createElement('div');
    state.className = 'muted small';
    state.textContent = ATTACHMENT_STATE_LABELS[volume.attachment.state] || volume.attachment.state;
    td.append(line, state);
    return td;
  }

  function volumePathCell(volume) {
    const td = document.createElement('td');
    if (volume.attachment && volume.attachment.device_path) {
      const code = document.createElement('code');
      code.textContent = volume.attachment.device_path;
      td.append(code);
    } else {
      td.textContent = '—';
    }
    return td;
  }

  function volumeActionsCell(volume, viewerAccountId, isAdmin, instances) {
    const td = document.createElement('td');
    if (volume.account_id !== viewerAccountId && !isAdmin) return td;

    if (volume.state === 'available') {
      const candidates = instances.filter((instance) => instance.account_id === volume.account_id
        && (instance.state === 'running' || instance.state === 'stopped'));
      if (candidates.length > 0) {
        const select = document.createElement('select');
        select.append(...candidates.map((instance) =>
          option(instance.instance_id, (instance.tags && instance.tags.Name) || instance.instance_id)));
        const attach = document.createElement('button');
        attach.type = 'button';
        attach.textContent = '接続';
        onAction(attach, 'click', async (event, scope) => {
          try {
            $('error').hidden = true;
            await api('POST', `/v1/volumes/${encodeURIComponent(volume.volume_id)}/attach`, { instance_id: select.value });
            delete td.closest('tr').dataset.dirty;
            announce('操作を受け付けました。状態の反映を確認しています。', scope);
            await Promise.all([loadVolumes(), loadCapacity()]);
          } catch (error) {
            showError(error, scope);
          }
        });
        const targetLabel = document.createElement('label');
        targetLabel.append('接続先 ', select);
        td.append(targetLabel, attach);
      } else {
        const noneNote = document.createElement('span');
        noneNote.className = 'muted small';
        noneNote.textContent = '接続先なし';
        td.append(noneNote);
      }

      const del = document.createElement('button');
      del.type = 'button';
      del.textContent = '削除';
      del.className = 'danger';
      onAction(del, 'click', async (event, scope) => {
        const label = (volume.tags && volume.tags.Name) || volume.volume_id;
        if (!await confirmAction({ title: 'ボリュームを削除', message: resourceDescription(volume, 'ボリューム') + '\n\nこのボリューム内のデータを削除します。取り消せません。', confirmLabel: 'このボリュームを削除', danger: true })) return;
        try {
          $('error').hidden = true;
          await api('DELETE', `/v1/volumes/${encodeURIComponent(volume.volume_id)}`);
          await Promise.all([loadVolumes(), loadCapacity()]);
        } catch (error) {
          showError(error, scope);
        }
      });
      td.append(del);
    }

    if (volume.state === 'in-use' && volume.attachment && volume.attachment.state === 'attached') {
      const detach = document.createElement('button');
      detach.type = 'button';
      detach.textContent = '切断';
      onAction(detach, 'click', async (event, scope) => {
        if (!await confirmAction({ message: 'ゲストでアンマウントしてから切断してください。切断を続けますか？', danger: true })) return;
        try {
          $('error').hidden = true;
          await api('POST', `/v1/volumes/${encodeURIComponent(volume.volume_id)}/detach`);
          await Promise.all([loadVolumes(), loadCapacity()]);
        } catch (error) {
          showError(error, scope);
        }
      });
      td.append(detach);
    }

    if (volume.state === 'available' || volume.state === 'in-use') {
      const resize = numberField('拡張後 GiB', 'size_gib', volume.size_gib, volume.size_gib + 1);
      if (effectiveLimits) resize.input.max = String(effectiveLimits.volume_size_gib.max);
      const grow = document.createElement('button');
      grow.type = 'button';
      grow.textContent = '拡張';
      onAction(grow, 'click', async (event, scope) => {
        const size = Number(resize.input.value);
        if (!Number.isInteger(size) || !(size > volume.size_gib) || (effectiveLimits && size > effectiveLimits.volume_size_gib.max)) {
          fieldError(resize.input, '拡張後の大きさは現在より大きい整数で、ボリューム上限以下にしてください。');
          return;
        }
        try {
          $('error').hidden = true;
          await api('PATCH', `/v1/volumes/${encodeURIComponent(volume.volume_id)}`, { size_gib: size });
            delete td.closest('tr').dataset.dirty;
            announce('操作を受け付けました。状態の反映を確認しています。', scope);
          await Promise.all([loadVolumes(), loadCapacity()]);
        } catch (error) {
          showError(error, scope);
        }
      });
      const discard = document.createElement('button');
      discard.type = 'button';
      discard.textContent = '入力を戻す';
      discard.addEventListener('click', () => { delete td.closest('tr').dataset.dirty; td.closest('tr').dataset.snapshot = ''; renderVolumes(); });
      td.append(resize.label, grow, discard);
    }
    return td;
  }

  function volumeRow(volume, viewerAccountId, isAdmin, instances) {
    const row = document.createElement('tr');
    row.dataset.resource = volume.volume_id;
    row.dataset.snapshot = JSON.stringify({ volume, instances });
    row.append(
      cell(volume.volume_id),
      cell((volume.tags && volume.tags.Name) || '—'),
      cell(volume.owner_username || volume.account_id),
      cell(volume.size_gib + ' GiB'),
      volumeStateCell(volume),
      volumeAttachmentCell(volume, instances),
      volumePathCell(volume),
      volumeActionsCell(volume, viewerAccountId, isAdmin, instances),
    );
    return row;
  }

  let lastVolumes = [];
  let volumeInstances = [];
  let volumesLoaded = false;
  let volumePollTimer = null;
  let volumeFailures = 0;
  function renderVolumes() {
    if (!volumesLoaded) return;
    const wrap = $('volumes-wrap');
    syncResourceRows($('volumes'), lastVolumes.map((volume) => volumeRow(volume, wrap.dataset.accountId, wrap.dataset.isAdmin === 'true', volumeInstances)), 8);
  }
  function scheduleVolumePoll(delay = 30000) {
    clearTimeout(volumePollTimer);
    if (!sessionExpired) volumePollTimer = setTimeout(loadVolumes, delay);
  }
  async function loadVolumes() {
    try {
      const [{ volumes }, { instances }] = await Promise.all([
        api('GET', '/v1/volumes'), api('GET', '/v1/instances'),
      ]);
      lastVolumes = volumes;
      volumeInstances = instances;
      volumesLoaded = true;
      volumeFailures = 0;
      renderVolumes();
      listStatus('volumes', `${volumes.length}個 · 最終更新 ${when(new Date())}`);
      const busy = volumes.some((volume) => VOLUME_TRANSIENT_STATES.has(volume.state) || volume.modification_state || (volume.attachment && volume.attachment.state !== 'attached'));
      scheduleVolumePoll(busy && !document.hidden ? 5000 : 30000);
    } catch (error) {
      loadProblem('volumes', error);
      scheduleVolumePoll(Math.min(60000, 5000 * (2 ** Math.min(++volumeFailures, 4))));
    }
  }

  onAction($('create-volume'), 'submit', async (submit, scope) => {
    submit.preventDefault();
    const form = new FormData(submit.target);
    const body = { size_gib: Number(form.get('size_gib')) };
    const name = form.get('name');
    if (name) body.tags = { Name: name };
    try {
      $('error').hidden = true;
      await api('POST', '/v1/volumes', body);
      submit.target.reset();
      await Promise.all([loadVolumes(), loadCapacity()]);
    } catch (error) {
      showError(error, scope);
    }
  });

  const PROTOCOL_LABELS = { tcp: 'TCP', udp: 'UDP', icmp: 'ICMP', icmpv6: 'ICMPv6', all: 'すべて' };

  function securityRuleTable(groupId, rules, canManage) {
    const table = document.createElement('table');
    const headRow = document.createElement('tr');
    headRow.append(...['プロトコル', 'ポート', '相手', '説明', '操作'].map((text, index) => {
      const th = document.createElement('th');
      if (index === 4) {
        const label = document.createElement('span');
        label.className = 'visually-hidden';
        label.textContent = text;
        th.append(label);
      } else {
        th.textContent = text;
      }
      return th;
    }));
    const thead = document.createElement('thead');
    thead.append(headRow);
    const tbody = document.createElement('tbody');
    for (const rule of rules) {
      const row = document.createElement('tr');
      let portText = 'すべて';
      if (rule.from_port !== undefined && rule.from_port !== null) {
        portText = rule.from_port === rule.to_port ? String(rule.from_port) : `${rule.from_port}-${rule.to_port}`;
      }
      row.append(
        cell(PROTOCOL_LABELS[rule.protocol] || rule.protocol),
        cell(portText),
        cell(rule.cidr),
        cell(rule.description || '—'),
      );
      const actionTd = document.createElement('td');
      if (canManage) {
        const del = document.createElement('button');
        del.type = 'button';
        del.textContent = '削除';
        del.className = 'danger';
        onAction(del, 'click', async (event, scope) => {
          if (!await confirmAction({ message: 'このルールを削除します。', danger: true })) return;
          try {
            $('error').hidden = true;
            await api('DELETE', `/v1/security-groups/${encodeURIComponent(groupId)}/rules/${encodeURIComponent(rule.rule_id)}`);
            await loadSecurityGroups();
          } catch (error) {
            showError(error, scope);
          }
        });
        actionTd.append(del);
      }
      row.append(actionTd);
      tbody.append(row);
    }
    table.append(thead, tbody);
    const scroll = document.createElement('div');
    scroll.className = 'scroll';
    scroll.append(table);
    return scroll;
  }

  // direction is fixed at construction time (one form per direction would be
  // simpler, but AWS-style groups treat 受信/送信 as one workflow with a
  // shared protocol/port/cidr shape, so a single form with a direction picker
  // matches how EC2's own console does it and halves the markup per group).
  function securityAddRuleForm(groupId) {
    const form = document.createElement('form');
    form.className = 'add-rule';

    const dirLabel = document.createElement('label');
    const dirSelect = document.createElement('select');
    dirSelect.append(option('ingress', '受信'), option('egress', '送信'));
    dirLabel.append('方向 ', dirSelect);

    const protoLabel = document.createElement('label');
    const protoSelect = document.createElement('select');
    protoSelect.append(
      option('tcp', 'tcp'), option('udp', 'udp'), option('icmp', 'icmp'),
      option('icmpv6', 'icmpv6'), option('all', 'すべて'),
    );
    protoLabel.append('プロトコル ', protoSelect);

    const fromField = numberField('開始ポート', 'from_port', '', 1);
    fromField.input.max = '65535';
    const toField = numberField('終了ポート', 'to_port', '', 1);
    toField.input.max = '65535';

    const cidrLabel = document.createElement('label');
    const cidrInput = document.createElement('input');
    cidrInput.value = '0.0.0.0/0';
    cidrInput.placeholder = '0.0.0.0/0';
    cidrLabel.append('相手 CIDR ', cidrInput);

    const descLabel = document.createElement('label');
    const descInput = document.createElement('input');
    descInput.maxLength = 256;
    descInput.placeholder = '任意';
    descLabel.append('説明 ', descInput);

    const submitButton = document.createElement('button');
    submitButton.type = 'submit';
    submitButton.textContent = '追加';

    function updatePortState() {
      const usesPorts = protoSelect.value === 'tcp' || protoSelect.value === 'udp';
      fromField.input.disabled = !usesPorts;
      toField.input.disabled = !usesPorts;
    }
    protoSelect.addEventListener('change', updatePortState);
    updatePortState();

    form.append(dirLabel, protoLabel, fromField.label, toField.label, cidrLabel, descLabel, submitButton);
    onAction(form, 'submit', async (submit, scope) => {
      submit.preventDefault();
      const protocol = protoSelect.value;
      const rule = { protocol, cidr: cidrInput.value || '0.0.0.0/0' };
      if (protocol === 'tcp' || protocol === 'udp') {
        const from = Number(fromField.input.value);
        if (!from) {
          fieldError(fromField.input, '開始ポートを入力してください');
          return;
        }
        rule.from_port = from;
        rule.to_port = toField.input.value ? Number(toField.input.value) : from;
      }
      if (descInput.value) rule.description = descInput.value;
      try {
        $('error').hidden = true;
        await api('POST', `/v1/security-groups/${encodeURIComponent(groupId)}/${dirSelect.value}`, { rules: [rule] });
        form.reset();
        updatePortState();
        await loadSecurityGroups();
      } catch (error) {
        showError(error, scope);
      }
    });
    return form;
  }

  function securityGroupCard(group, viewerAccountId, isAdmin) {
    const card = document.createElement('div');
    card.className = 'group-card';

    const head = document.createElement('div');
    head.className = 'group-head';
    const title = document.createElement('strong');
    title.textContent = group.group_name;
    head.append(title);
    if (group.is_default) {
      const badge = document.createElement('span');
      badge.className = 'badge';
      badge.textContent = '既定';
      head.append(badge);
    }
    const owner = document.createElement('span');
    owner.className = 'muted';
    owner.textContent = group.owner_username || group.account_id;
    head.append(owner);
    const count = document.createElement('span');
    count.className = 'muted';
    count.textContent = `使用中のインスタンス ${(group.instance_ids || []).length}`;
    head.append(count);
    card.append(head);

    if (group.description) {
      const desc = document.createElement('p');
      desc.className = 'muted small';
      desc.textContent = group.description;
      card.append(desc);
    }

    const canManage = group.account_id === viewerAccountId || isAdmin;

    const ingressHeading = document.createElement('h3');
    ingressHeading.textContent = '受信';
    const egressHeading = document.createElement('h3');
    egressHeading.textContent = '送信';
    card.append(
      ingressHeading, securityRuleTable(group.group_id, group.ingress, canManage),
      egressHeading, securityRuleTable(group.group_id, group.egress, canManage),
    );

    if (canManage) {
      card.append(securityAddRuleForm(group.group_id));
      if (!group.is_default) {
        const del = document.createElement('button');
        del.type = 'button';
        del.textContent = 'グループを削除';
        del.className = 'danger';
        onAction(del, 'click', async (event, scope) => {
          if (!await confirmAction({ message: `セキュリティグループ「${group.group_name}」を削除します。`, danger: true })) return;
          try {
            $('error').hidden = true;
            await api('DELETE', `/v1/security-groups/${encodeURIComponent(group.group_id)}`);
            await loadSecurityGroups();
          } catch (error) {
            showError(error, scope);
          }
        });
        card.append(del);
      }
    }

    return card;
  }

  // Also refills the create-instance checklist, since the two always need
  // the same "which groups does this account own" answer.
  function updateCreateInstanceGroupOptions(groups, viewerAccountId) {
    const container = $('create-instance-groups');
    if (!container) return;
    const own = groups.filter((group) => group.account_id === viewerAccountId);
    container.replaceChildren(...own.map((group) => {
      const label = document.createElement('label');
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.name = 'security_group_ids';
      input.value = group.group_id;
      label.append(input, group.group_name);
      return label;
    }));
  }

  async function loadSecurityGroups() {
    const wrap = $('security-groups-wrap');
    const viewerAccountId = wrap.dataset.accountId;
    const isAdmin = wrap.dataset.isAdmin === 'true';
    try {
      const { security_groups: groups } = await api('GET', '/v1/security-groups');
      lastSecurityGroups = groups;
      $('security-groups').replaceChildren(...groups.map((group) => securityGroupCard(group, viewerAccountId, isAdmin)));
      updateCreateInstanceGroupOptions(groups, viewerAccountId);
      readiness.groups = true;
      updateReadiness();
    } catch (error) {
      lastSecurityGroups = [];
      readiness.groups = false;
      updateReadiness();
      $('security-groups').replaceChildren(note(error.message));
    }
  }

  onAction($('create-security-group'), 'submit', async (submit, scope) => {
    submit.preventDefault();
    const form = new FormData(submit.target);
    const body = { group_name: form.get('group_name') };
    const description = form.get('description');
    if (description) body.description = description;
    try {
      $('error').hidden = true;
      await api('POST', '/v1/security-groups', body);
      submit.target.reset();
      await loadSecurityGroups();
    } catch (error) {
      showError(error, scope);
    }
  });

  // Buckets and S3 keys.
  let lastS3Keys = [];

  function bucketKeyList(bucket, canManage) {
    const wrap = document.createElement('div');
    if (!bucket.keys || bucket.keys.length === 0) {
      const none = document.createElement('span');
      none.className = 'muted small';
      none.textContent = '許可されたキーはありません';
      wrap.append(none);
      return wrap;
    }
    for (const key of bucket.keys) {
      const line = document.createElement('div');
      line.className = 'small';
      const perms = [key.read && '読み取り', key.write && '読み書き', key.owner && 'owner'].filter(Boolean).join('・') || '権限なし';
      const label = document.createElement('span');
      label.textContent = `${key.key_name || key.key_id}（${perms}）`;
      line.append(label);
      if (canManage) {
        const revoke = document.createElement('button');
        revoke.type = 'button';
        revoke.textContent = '剥奪';
        revoke.className = 'danger';
        onAction(revoke, 'click', async (event, scope) => {
          try {
            $('error').hidden = true;
            await api('DELETE', `/v1/buckets/${encodeURIComponent(bucket.bucket_name)}/keys/${encodeURIComponent(key.key_id)}`);
            await loadBuckets();
          } catch (error) {
            showError(error, scope);
          }
        });
        line.append(revoke);
      }
      wrap.append(line);
    }
    return wrap;
  }

  // The permission picker starts from the common purpose (review-only or
  // read/write). owner is never selected by default: it manages the bucket and
  // its grants, so it takes an explicit choice under 詳細指定.
  function bucketAllowForm(bucket) {
    const form = document.createElement('form');
    form.className = 'inline';
    const select = document.createElement('select');
    select.name = 'key_id';
    for (const key of lastS3Keys) {
      select.append(option(key.key_id, key.name || key.key_id));
    }
    const keyLabel = document.createElement('label');
    keyLabel.append('キー ', select);

    const purpose = document.createElement('select');
    purpose.name = 'purpose';
    purpose.append(option('read', '読み取り'), option('write', '読み書き'), option('custom', '詳細指定'));
    const purposeLabel = document.createElement('label');
    purposeLabel.append('用途 ', purpose);

    const permission = (name, text, help) => {
      const wrapper = document.createElement('label');
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.name = name;
      input.checked = name === 'read';
      wrapper.append(input, text);
      wrapper.title = help;
      return { wrapper, input };
    };
    const read = permission('read', '読み取り', 'オブジェクトの取得と一覧');
    const write = permission('write', '書き込み', 'オブジェクトの追加・更新・削除');
    const owner = permission('owner', 'owner（バケット管理）', 'バケット設定と権限の管理。必要なときだけ付けてください');
    owner.input.checked = false;

    const detail = document.createElement('div');
    detail.className = 'checklist';
    const meaning = document.createElement('p');
    meaning.className = 'muted small';
    detail.append(read.wrapper, write.wrapper, owner.wrapper, meaning);

    const update = () => {
      if (purpose.value === 'read') {
        read.input.checked = true; write.input.checked = false; owner.input.checked = false;
        detail.hidden = true;
      } else if (purpose.value === 'write') {
        read.input.checked = true; write.input.checked = true; owner.input.checked = false;
        detail.hidden = true;
      } else {
        detail.hidden = false;
      }
      const chosen = [
        read.input.checked && '読み取り',
        write.input.checked && '書き込み',
        owner.input.checked && 'owner（バケット管理）',
      ].filter(Boolean).join('・') || '権限なし';
      const keyName = select.selectedOptions[0]?.textContent || select.value;
      meaning.textContent = `バケット「${bucket.bucket_name}」のキー「${keyName}」に「${chosen}」を許可します。owner はバケットと権限を管理できる強い権限です。`;
    };
    purpose.addEventListener('change', update);
    select.addEventListener('change', update);
    update();

    const button = document.createElement('button');
    button.type = 'submit';
    button.textContent = '許可';
    form.append(keyLabel, purposeLabel, detail, button);
    onAction(form, 'submit', async (submit, scope) => {
      submit.preventDefault();
      const data = new FormData(form);
      const granted = {
        read: data.get('read') === 'on',
        write: data.get('write') === 'on',
        owner: data.get('owner') === 'on',
      };
      const keyName = select.selectedOptions[0]?.textContent || select.value;
      const chosen = [granted.read && '読み取り', granted.write && '書き込み', granted.owner && 'owner']
        .filter(Boolean).join('・') || '権限なし';
      if (!await confirmAction({ title: 'S3キーの権限',
        message: `バケット「${bucket.bucket_name}」のキー「${keyName}」に「${chosen}」を許可します。` })) return;
      try {
        $('error').hidden = true;
        await api('PUT', `/v1/buckets/${encodeURIComponent(bucket.bucket_name)}/keys/${encodeURIComponent(data.get('key_id'))}`, granted);
        announce('S3キーの権限を更新しました。', scope);
        await loadBuckets();
      } catch (error) {
        showError(error, scope);
      }
    });
    return form;
  }

  function bucketCard(bucket, viewerAccountId, isAdmin) {
    const card = document.createElement('div');
    card.className = 'group-card';
    const head = document.createElement('div');
    head.className = 'group-head';
    const title = document.createElement('strong');
    title.textContent = bucket.bucket_name;
    head.append(title);
    const owner = document.createElement('span');
    owner.className = 'muted';
    owner.textContent = bucket.owner_username || bucket.account_id;
    head.append(owner);
    const stats = document.createElement('span');
    stats.className = 'muted';
    stats.textContent = `${bucket.objects} objects / ${bucket.bytes} bytes`;
    head.append(stats);
    card.append(head);

    const endpoint = document.createElement('p');
    endpoint.className = 'muted small';
    endpoint.textContent = `S3エンドポイント ${bucket.s3_endpoint}（region ${bucket.s3_region}）`;
    card.append(endpoint);

    const canManage = bucket.account_id === viewerAccountId || isAdmin;
    card.append(bucketKeyList(bucket, canManage));
    if (canManage) {
      if (lastS3Keys.length > 0) card.append(bucketAllowForm(bucket));
      const del = document.createElement('button');
      del.type = 'button';
      del.textContent = 'バケットを削除';
      del.className = 'danger';
      onAction(del, 'click', async (event, scope) => {
        if (!await confirmAction({ title: 'S3バケットを削除',
          message: `バケット: ${bucket.bucket_name}\n所有者: ${bucket.owner_username || bucket.account_id}\nオブジェクト: ${bucket.objects}個 / ${bucket.bytes} bytes\n\n中身が残っていると削除に失敗します。取り消せません。`,
          confirmLabel: 'このバケットを削除', danger: true })) return;
        try {
          $('error').hidden = true;
          await api('DELETE', `/v1/buckets/${encodeURIComponent(bucket.bucket_name)}`);
          await loadBuckets();
        } catch (error) {
          showError(error, scope);
        }
      });
      card.append(del);
    }
    return card;
  }

  async function loadBuckets() {
    const wrap = $('buckets-wrap');
    if (!wrap) return;
    const viewerAccountId = wrap.dataset.accountId;
    const isAdmin = wrap.dataset.isAdmin === 'true';
    try {
      const [{ buckets }, { s3_keys: keys }] = await Promise.all([
        api('GET', '/v1/buckets'),
        api('GET', '/v1/s3-keys'),
      ]);
      lastS3Keys = keys;
      $('buckets').replaceChildren(...buckets.map((bucket) => bucketCard(bucket, viewerAccountId, isAdmin)));
    } catch (error) {
      $('buckets').replaceChildren(note(error.message));
    }
  }

  async function loadS3Keys() {
    const tbody = $('s3-keys');
    if (!tbody) return;
    try {
      const { s3_keys: keys } = await api('GET', '/v1/s3-keys');
      lastS3Keys = keys;
      tbody.replaceChildren(...keys.map((key) => {
        const row = document.createElement('tr');
        const del = document.createElement('button');
        del.type = 'button';
        del.textContent = '削除';
        del.className = 'danger';
        onAction(del, 'click', async (event, scope) => {
          if (!await confirmAction({ title: 'S3キーを削除',
            message: `キー「${key.name}」（${key.key_id}）を削除します。このキーに与えた権限も消えます。取り消せません。`,
            confirmLabel: 'このキーを削除', danger: true })) return;
          try {
            $('error').hidden = true;
            await api('DELETE', `/v1/s3-keys/${encodeURIComponent(key.key_id)}`);
            await Promise.all([loadS3Keys(), loadBuckets()]);
          } catch (error) {
            showError(error, scope);
          }
        });
        const actions = document.createElement('td');
        actions.append(del);
        row.append(cell(key.key_id), cell(key.name), cell(when(key.created_at)), actions);
        return row;
      }));
    } catch (error) {
      tbody.replaceChildren(note(error.message));
    }
  }

  const createBucketForm = $('create-bucket');
  if (createBucketForm) {
    onAction(createBucketForm, 'submit', async (submit, scope) => {
      submit.preventDefault();
      const data = new FormData(createBucketForm);
      try {
        $('error').hidden = true;
        await api('POST', '/v1/buckets', { bucket_name: data.get('bucket_name') });
        createBucketForm.reset();
        await loadBuckets();
      } catch (error) {
        showError(error, scope);
      }
    });
  }

  const createS3KeyForm = $('create-s3-key');
  if (createS3KeyForm) {
    onAction(createS3KeyForm, 'submit', async (submit, scope) => {
      submit.preventDefault();
      const data = new FormData(createS3KeyForm);
      try {
        $('error').hidden = true;
        const { s3_key: key } = await api('POST', '/v1/s3-keys', { name: data.get('name') });
        createS3KeyForm.reset();
        if (key.secret_access_key) {
          $('new-s3-secret-value').textContent = `${key.key_id}\n${key.secret_access_key}`;
          $('new-s3-secret').hidden = false;
          blockForm(createS3KeyForm, true);
        }
        try {
          await Promise.all([loadS3Keys(), loadBuckets()]);
        } catch (error) {
          announce(`キーは発行・表示できていますが、一覧を更新できませんでした。${error.message}`, scope);
        }
      } catch (error) {
        showError(error, scope);
      }
    });
  }

  $('dismiss-s3-secret').addEventListener('click', () => {
    $('new-s3-secret-value').textContent = '';
    $('new-s3-secret').hidden = true;
    blockForm(createS3KeyForm, false);
  });

  if ($('copy-s3-secret')) {
    onAction($('copy-s3-secret'), 'click', async () => { await copyText($('new-s3-secret-value').textContent, $('s3-view')); });
  }

  // GET /v1/limits is readable by every caller (only PUT is admin-only), so
  // the create-volume form's min/max come from here even for non-admins. The
  // form itself (below) only exists in the DOM for admins. Saving the form
  // replaces every override at once, so the confirmation spells out both the
  // values that change and the overrides an empty field returns to default.
  let lastLimits = null;

  function limitsReady(ready) {
    const form = $('limits');
    if (!form) return;
    form.dataset.loaded = String(ready);
    blockForm(form, !ready);
    const reset = $('reset-limits');
    if (reset) { reset.dataset.blocked = String(!ready); reset.disabled = !ready; }
  }

  async function loadLimits() {
    try {
      const data = await api('GET', '/v1/limits');
      lastLimits = data;
      effectiveLimits = data.limits;
      readiness.limits = true;
      updateReadiness();
      const sizeInput = document.querySelector('#create-volume input[name="size_gib"]');
      const bounds = data.limits && data.limits.volume_size_gib;
      if (sizeInput && bounds) {
        sizeInput.min = String(bounds.min);
        sizeInput.max = String(bounds.max);
      }
      const rootDiskInput = document.querySelector('#create-instance input[name="root_disk_gib"]');
      const rootDisk = data.limits && data.limits.root_disk_gib;
      if (rootDiskInput && rootDisk) {
        rootDiskInput.min = String(rootDisk.min);
        rootDiskInput.max = String(rootDisk.max);
        rootDiskInput.placeholder = `既定 ${rootDisk.default}`;
      }
      maxImageGiB = data.limits && data.limits.capacity ? data.limits.capacity.max_image_gib : 0;
      if ($('upload-limit')) {
        $('upload-limit').textContent = maxImageGiB
          ? `アップロードできるファイルは1つ ${maxImageGiB} GiB までです。`
          : 'アップロードできるファイルの大きさに、この画面からの上限はありません。';
      }
      if (!$('limits')) return;
      for (const input of $('limits').querySelectorAll('input[name]')) {
        const [group, field] = input.name.split('.');
        const override = (data.overrides[group] || {})[field];
        input.value = override === undefined || override === null ? '' : override;
        input.placeholder = `既定 ${data.defaults[group][field]}`;
      }
      $('limits-status').textContent = data.updated_at
        ? `最後の変更: ${when(data.updated_at)}${data.updated_by ? '（アカウント ' + data.updated_by + '）' : ''}`
        : '既定値のままです。';
      limitsReady(true);
    } catch (error) {
      lastLimits = null;
      effectiveLimits = null;
      readiness.limits = false;
      updateReadiness();
      if ($('limits-status')) {
        $('limits-status').textContent = `${error.message} 値を取得できないため保存できません。「表示を更新」で再取得してください。`;
      }
      limitsReady(false);
    }
  }

  function limitsInputLabel(input) {
    const label = input.closest('label');
    if (!label) return input.name;
    return label.firstChild?.textContent?.trim() || input.name;
  }

  async function saveLimits(patch, scope) {
    try {
      $('error').hidden = true;
      await api('PUT', '/v1/limits', patch);
      if ($('limits')) delete $('limits').dataset.dirty;
      announce('上限を保存しました。', scope);
      await Promise.all([loadLimits(), loadCapacity()]);
    } catch (error) {
      showError(error, scope);
    }
  }

  if ($('limits')) {
    onAction($('limits'), 'submit', async (submit, scope) => {
      submit.preventDefault();
      const patch = {};
      const changes = [];
      for (const input of $('limits').querySelectorAll('input[name]')) {
        const [group, field] = input.name.split('.');
        const typed = input.value.trim();
        const effective = lastLimits?.limits?.[group]?.[field];
        const fallback = lastLimits?.defaults?.[group]?.[field];
        const overridden = lastLimits?.overrides?.[group]?.[field] !== undefined;
        if (typed === '') {
          if (overridden) changes.push(`${limitsInputLabel(input)}: ${effective} → 既定 ${fallback}`);
          continue;
        }
        if (Number(typed) === effective && !overridden) continue;
        patch[group] = patch[group] || {};
        patch[group][field] = Number(typed);
        changes.push(`${limitsInputLabel(input)}: ${effective} → ${typed}${overridden ? '' : '（既定へ上書き）'}`);
      }
      if (changes.length === 0) { announce('変更はありません。', scope); return; }
      if (!await confirmAction({ title: '上限の変更内容',
        message: 'このフォーム全体を保存します。\n\n' + changes.join('\n') + '\n\n空欄にした項目は既定値へ戻ります。',
        confirmLabel: 'この内容で保存' })) return;
      await saveLimits(patch, scope);
    });
    onAction($('reset-limits'), 'click', async (event, scope) => {
      if (!await confirmAction({ message: 'すべての上書きを消し、既定値へ戻します。', danger: true })) return;
      await saveLimits({}, scope);
    });
  }

  const refresh = () => Promise.all([
    loadKeys(), loadEvents(), loadCapacity(), loadLimits(), loadInstances(), loadImages(), loadISOs(), loadKeyPairs(),
    loadVolumes(), loadSecurityGroups(), loadBuckets(), loadS3Keys(),
  ]);

  onAction($('refresh-all'), 'click', async () => {
    $('refresh-status').textContent = '更新中…';
    try {
      await refresh();
      $('refresh-status').textContent = `最終更新 ${when(new Date())}`;
    } catch (error) {
      $('refresh-status').textContent = '更新できませんでした。';
      showError(error);
    }
  });

  const createKeyForm = $('create-key');
  onAction(createKeyForm, 'submit', async (submit, scope) => {
    submit.preventDefault();
    const form = new FormData(createKeyForm);
    const body = { description: form.get('description') };
    if (form.get('expires_in_days')) body.expires_in_days = Number(form.get('expires_in_days'));
    try {
      $('error').hidden = true;
      const created = await api('POST', '/v1/access-keys', body);
      createKeyForm.reset();
      $('new-secret-value').textContent = created.secret_access_key;
      $('new-secret-usage').textContent =
        `export SHAKECLOUD_ACCESS_KEY='${created.secret_access_key}'\n` +
        `curl -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" ${location.origin}/v1/caller-identity`;
      $('new-secret').hidden = false;
      // Hold further issuance until this one-time value is acknowledged, so a
      // second click cannot overwrite a secret the person has not saved yet.
      blockForm(createKeyForm, true);
      try {
        await refresh();
      } catch (error) {
        announce(`キーは発行・表示できていますが、一覧を更新できませんでした。${error.message}`, scope);
      }
    } catch (error) {
      showError(error, scope);
    }
  });

  if ($('copy-secret')) {
    onAction($('copy-secret'), 'click', async () => { await copyText($('new-secret-value').textContent, $('keys-view')); });
  }

  onAction($('import-key-pair'), 'submit', async (submit, scope) => {
    submit.preventDefault();
    const form = new FormData(submit.target);
    const body = { key_name: form.get('key_name'), public_key: form.get('public_key') };
    try {
      $('error').hidden = true;
      await api('POST', '/v1/key-pairs', body);
      submit.target.reset();
      await loadKeyPairs();
    } catch (error) {
      showError(error, scope);
    }
  });

  // Uses XMLHttpRequest instead of the shared api() helper because it needs
  // upload progress events, which fetch() cannot provide. The request/error
  // shape mirrors api() by hand: parse the same {error:{code,message}} body,
  // and bounce to / on 401 like api() does. Transfer completion and server
  // validation are shown as separate stages; aborting stops the browser
  // transfer only, so the message does not claim the server stopped.
  let uploadXHR = null;
  $('cancel-upload').addEventListener('click', () => { uploadXHR?.abort(); });

  $('upload-image').addEventListener('submit', (submit) => {
    submit.preventDefault();
    if (uploadXHR) return;
    const form = submit.target;
    const file = form.elements.file.files[0];
    if (!file) return;
    if (maxImageGiB && file.size > maxImageGiB * 1024 ** 3) {
      showError(new Error(`ファイルが大きすぎます。1つ ${maxImageGiB} GiB 以下にしてください。`), form);
      return;
    }
    const data = new FormData();
    data.append('name', form.elements.name.value);
    data.append('file', file);

    const progress = $('upload-progress');
    const status = $('upload-status');
    const cancel = $('cancel-upload');
    const submitButton = form.querySelector('button[type="submit"]');
    $('error').hidden = true;
    progress.value = 0;
    progress.hidden = false;
    cancel.hidden = false;
    submitButton.disabled = true;
    status.textContent = '転送中… 0%';

    const xhr = new XMLHttpRequest();
    uploadXHR = xhr;
    xhr.open('POST', '/v1/images');
    xhr.withCredentials = true;
    // No xhr.timeout: uploads of large images can legitimately take minutes.
    const finish = () => {
      uploadXHR = null;
      cancel.hidden = true;
      progress.hidden = true;
      submitButton.disabled = !readiness.limits;
    };
    xhr.upload.addEventListener('progress', (event) => {
      if (!event.lengthComputable) return;
      const percent = Math.round((event.loaded / event.total) * 100);
      progress.value = percent;
      status.textContent = `転送中… ${percent}%`;
    });
    xhr.upload.addEventListener('load', () => {
      progress.value = 100;
      status.textContent = '転送が完了しました。サーバーで検証・登録しています…';
    });
    xhr.addEventListener('load', async () => {
      finish();
      if (xhr.status === 401) {
        sessionExpired = true;
        $('session-expired').hidden = false;
        return;
      }
      if (xhr.status === 201) {
        status.textContent = '検証と登録が完了しました。';
        form.reset();
        await Promise.all([loadImages(), loadCapacity()]);
        return;
      }
      const error = new Error(`アップロードに失敗しました（HTTP ${xhr.status}）。${xhr.status === 413 ? 'ファイルの大きさを確認してください。' : ''}`);
      try {
        const body = JSON.parse(xhr.responseText);
        error.detail = body.error?.message ? `${body.error.message}（${body.error.code || xhr.status}）` : `HTTP ${xhr.status}`;
        error.requestID = body.request_id;
      } catch (_) {
        error.detail = `HTTP ${xhr.status}`;
      }
      showError(error, form);
    });
    xhr.addEventListener('error', () => {
      finish();
      showError(new Error('転送中に通信エラーが発生しました。操作結果が不明です。一覧を更新して確認してください。'), form);
    });
    xhr.addEventListener('abort', () => {
      finish();
      status.textContent = '転送を中断しました。サーバー側で検証が続いている場合があります。一覧を更新して確認してください。';
    });
    xhr.send(data);
  });

  // ISO upload. The same XHR pattern as an image, with the os field that
  // decides the hardware when the ISO is used to install.
  let isoUploadXHR = null;
  $('cancel-iso-upload').addEventListener('click', () => { isoUploadXHR?.abort(); });
  $('upload-iso').addEventListener('submit', (submit) => {
    submit.preventDefault();
    if (isoUploadXHR) return;
    const form = submit.target;
    const file = form.elements.file.files[0];
    if (!file) return;
    const data = new FormData();
    data.append('name', form.elements.name.value);
    data.append('os', form.elements.os.value);
    data.append('file', file);
    const progress = $('iso-upload-progress');
    const status = $('iso-upload-status');
    const cancel = $('cancel-iso-upload');
    const submitButton = form.querySelector('button[type="submit"]');
    $('error').hidden = true;
    progress.value = 0;
    progress.hidden = false;
    cancel.hidden = false;
    submitButton.disabled = true;
    status.textContent = '転送中… 0%';
    const xhr = new XMLHttpRequest();
    isoUploadXHR = xhr;
    xhr.open('POST', '/v1/isos');
    xhr.withCredentials = true;
    const finish = () => {
      isoUploadXHR = null;
      cancel.hidden = true;
      progress.hidden = true;
      submitButton.disabled = !readiness.limits;
    };
    xhr.upload.addEventListener('progress', (event) => {
      if (!event.lengthComputable) return;
      const percent = Math.round((event.loaded / event.total) * 100);
      progress.value = percent;
      status.textContent = `転送中… ${percent}%`;
    });
    xhr.upload.addEventListener('load', () => {
      progress.value = 100;
      status.textContent = '転送が完了しました。サーバーで登録しています…';
    });
    xhr.addEventListener('load', async () => {
      finish();
      if (xhr.status === 401) {
        sessionExpired = true;
        $('session-expired').hidden = false;
        return;
      }
      if (xhr.status === 201) {
        status.textContent = '登録しました。';
        form.reset();
        await loadISOs();
        return;
      }
      const error = new Error(`アップロードに失敗しました（HTTP ${xhr.status}）。${xhr.status === 413 ? '大きさを確認してください。' : ''}`);
      try {
        const body = JSON.parse(xhr.responseText);
        error.detail = body.error?.message ? `${body.error.message}（${body.error.code || xhr.status}）` : `HTTP ${xhr.status}`;
        error.requestID = body.request_id;
      } catch (_) {
        error.detail = `HTTP ${xhr.status}`;
      }
      showError(error, form);
    });
    xhr.addEventListener('error', () => {
      finish();
      showError(new Error('転送中に通信エラーが発生しました。一覧を更新して確認してください。'), form);
    });
    xhr.addEventListener('abort', () => {
      finish();
      status.textContent = '転送を中断しました。一覧を更新して確認してください。';
    });
    xhr.send(data);
  });

  $('dismiss-secret').addEventListener('click', () => {
    $('new-secret-value').textContent = '';
    $('new-secret-usage').textContent = '';
    $('new-secret').hidden = true;
    blockForm(createKeyForm, false);
  });

  onAction($('logout'), 'click', async (event, scope) => {
    try {
      await api('POST', '/auth/logout');
    } finally {
      location.href = '/';
    }
  });

  window.PortalUI.init();
  loadInstanceTypes();
  refresh().catch(showError);
})();
