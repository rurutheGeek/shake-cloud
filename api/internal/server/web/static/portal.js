'use strict';
// The self-service portal. It uses the same JSON API as Terraform and the CLI,
// authenticated by the session cookie, and holds no state of its own.
(() => {
  const $ = (id) => document.getElementById(id);
  if (!$('keys')) return; // logged out

  const when = (value) => (value ? new Date(value).toLocaleString('ja-JP') : '—');
  const cell = (text) => {
    const td = document.createElement('td');
    td.textContent = text;
    return td;
  };

  async function api(method, path, body) {
    const init = { method, credentials: 'same-origin', headers: {} };
    if (body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    const response = await fetch(path, init);
    if (response.status === 401) {
      location.href = '/';
      throw new Error('ログインの有効期限が切れました');
    }
    if (response.status === 204) return null;
    const data = await response.json();
    if (!response.ok) {
      throw new Error(`${data.error.message}（${data.error.code}、request ${data.request_id}）`);
    }
    return data;
  }

  function showError(error) {
    $('error').textContent = error.message;
    $('error').hidden = false;
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
      button.textContent = '削除';
      button.addEventListener('click', async () => {
        if (!confirm(`キー ${key.access_key_id} を削除します。このキーを使っている Terraform や CLI は動かなくなります。`)) return;
        try {
          $('error').hidden = true;
          await api('DELETE', `/v1/access-keys/${encodeURIComponent(key.access_key_id)}`);
          await refresh();
        } catch (error) {
          showError(error);
        }
      });
      const action = document.createElement('td');
      action.append(button);
      row.append(action);
      return row;
    });
    $('keys').replaceChildren(...rows);
  }

  async function loadEvents() {
    const { events } = await api('GET', '/v1/audit-events?max_results=20');
    $('events').replaceChildren(...events.map((event) => {
      const row = document.createElement('tr');
      row.append(
        cell(when(event.event_time)),
        cell(event.event_name),
        cell(event.error_code || '成功'),
        cell(event.account_id || '—'),
        cell(event.access_key_id || '—'),
        cell(event.source_ip_address),
      );
      return row;
    }));
  }

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
      $('capacity').replaceChildren(note(error.message));
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
    const owner = image.public ? '共有' : (image.owner_username || image.account_id);
    row.append(
      cell(image.name),
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
      button.addEventListener('click', async () => {
        if (!confirm(`イメージ「${image.name}」を削除します。すでにこのイメージから作ったVMには影響しません（ディスクはコピーされています）。`)) return;
        try {
          $('error').hidden = true;
          await api('DELETE', `/v1/images/${encodeURIComponent(image.image_id)}`);
          await Promise.all([loadImages(), loadCapacity()]);
        } catch (error) {
          showError(error);
        }
      });
      actions.append(button);
    }
    row.append(actions);
    return row;
  }

  async function loadImages() {
    const select = document.querySelector('#create-instance select[name="image_id"]');
    const wrap = $('images-wrap');
    const viewerAccountId = wrap.dataset.accountId;
    const isAdmin = wrap.dataset.isAdmin === 'true';
    try {
      const { images } = await api('GET', '/v1/images');
      select.replaceChildren(...images.map((image) => option(image.image_id, image.name)));
      $('images').replaceChildren(...images.map((image) => imageRow(image, viewerAccountId, isAdmin)));
    } catch (error) {
      select.replaceChildren(option('', '取得できません'));
      const row = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 6;
      td.className = 'muted';
      td.textContent = error.message;
      row.append(td);
      $('images').replaceChildren(row);
    }
  }

  function keyPairRow(keyPair) {
    const row = document.createElement('tr');
    row.append(cell(keyPair.key_name), cell(keyPair.fingerprint), cell(when(keyPair.created_at)));
    const actions = document.createElement('td');
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = '削除';
    button.addEventListener('click', async () => {
      if (!confirm(`SSH鍵「${keyPair.key_name}」を削除します。すでにこの鍵で作ったVMはそのまま使えます（鍵は作成時にVMへ書き込み済みです）。`)) return;
      try {
        $('error').hidden = true;
        await api('DELETE', `/v1/key-pairs/${encodeURIComponent(keyPair.key_name)}`);
        await loadKeyPairs();
      } catch (error) {
        showError(error);
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
      select.replaceChildren(placeholder, ...keyPairs.map((keyPair) => option(keyPair.key_name, keyPair.key_name)));
      $('key-pairs').replaceChildren(...keyPairs.map(keyPairRow));
    } catch (error) {
      select.replaceChildren(placeholder);
      const row = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 4;
      td.className = 'muted';
      td.textContent = error.message;
      row.append(td);
      $('key-pairs').replaceChildren(row);
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
      // Leave only the "指定しない" option; explicit numbers still work.
    }
  }

  function powerButton(label, path, enabled) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.disabled = !enabled;
    button.addEventListener('click', async () => {
      try {
        $('error').hidden = true;
        await api('POST', path);
        await Promise.all([loadInstances(), loadCapacity()]);
      } catch (error) {
        showError(error);
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
    button.addEventListener('click', async () => {
      const win = window.open('about:blank', '_blank');
      try {
        $('error').hidden = true;
        const id = encodeURIComponent(instance.instance_id);
        const data = await api('POST', `/v1/instances/${id}/console`);
        if (win) win.location.href = data.console.url;
      } catch (error) {
        if (win) win.close();
        showError(error);
      }
    });
    return button;
  }

  function deleteInstanceButton(instance) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = '削除';
    button.disabled = instance.state === 'terminated';
    button.addEventListener('click', async () => {
      const label = (instance.tags && instance.tags.Name) || instance.instance_id;
      if (!confirm(`インスタンス「${label}」を削除します。`)) return;
      try {
        $('error').hidden = true;
        await api('DELETE', `/v1/instances/${encodeURIComponent(instance.instance_id)}`);
        await Promise.all([loadInstances(), loadCapacity()]);
      } catch (error) {
        showError(error);
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

  function closeEditRows() {
    for (const editRow of $('instances').querySelectorAll('tr.edit-row')) editRow.remove();
  }

  // The admin-only inline edit row. PATCH only carries fields that actually
  // changed; the API itself enforces which fields may change while running.
  function toggleEditRow(row, instance) {
    const already = row.nextElementSibling;
    if (already && already.classList.contains('edit-row')) {
      already.remove();
      return;
    }
    closeEditRows();

    const vcpus = numberField('vCPU', 'vcpus', instance.vcpus, 1);
    const memory = numberField('メモリ MiB', 'memory_mib', instance.memory_mib, 512);
    // min is 0, not 512: a fixed-memory (ballooning off) instance already sits
    // at memory_min_mib 0, and a min above the current value would make the
    // browser refuse to submit the form at all.
    const memoryMin = numberField('最小メモリ MiB', 'memory_min_mib', instance.memory_min_mib, 0);
    const disk = numberField('ルートディスク GiB', 'root_disk_gib', instance.root_disk_gib, instance.root_disk_gib);

    const ballooningLabel = document.createElement('label');
    const ballooningInput = document.createElement('input');
    ballooningInput.type = 'checkbox';
    ballooningInput.checked = instance.ballooning;
    ballooningLabel.append(ballooningInput, ' バルーニングを使う');

    const hint = document.createElement('p');
    hint.className = 'muted small wide';
    hint.textContent = 'vCPU・メモリ・バルーニングの変更は停止中のインスタンスだけです。ディスクは拡大のみできます。';

    const save = document.createElement('button');
    save.type = 'submit';
    save.textContent = '保存';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.textContent = 'やめる';

    const form = document.createElement('form');
    form.className = 'edit-instance';
    form.append(vcpus.label, memory.label, memoryMin.label, ballooningLabel, disk.label, hint, save, cancel);

    cancel.addEventListener('click', () => editRow.remove());
    form.addEventListener('submit', async (submit) => {
      submit.preventDefault();
      const patch = {};
      if (Number(vcpus.input.value) !== instance.vcpus) patch.vcpus = Number(vcpus.input.value);
      if (Number(memory.input.value) !== instance.memory_mib) patch.memory_mib = Number(memory.input.value);
      if (Number(memoryMin.input.value) !== instance.memory_min_mib) patch.memory_min_mib = Number(memoryMin.input.value);
      if (ballooningInput.checked !== instance.ballooning) patch.ballooning = ballooningInput.checked;
      if (Number(disk.input.value) !== instance.root_disk_gib) patch.root_disk_gib = Number(disk.input.value);
      try {
        $('error').hidden = true;
        await api('PATCH', `/v1/instances/${encodeURIComponent(instance.instance_id)}`, patch);
        editRow.remove();
        await Promise.all([loadInstances(), loadCapacity()]);
      } catch (error) {
        showError(error);
      }
    });

    const editRow = document.createElement('tr');
    editRow.className = 'edit-row';
    const td = document.createElement('td');
    td.colSpan = 9;
    td.append(form);
    editRow.append(td);
    row.after(editRow);
  }

  // The security-groups edit row, open to the instance's owner as well as an
  // admin (unlike the resource edit row above, which is admin-only). Shares
  // the .edit-row slot with it via closeEditRows(), so at most one edit row
  // is open per table at a time.
  function toggleGroupEditRow(row, instance) {
    const already = row.nextElementSibling;
    if (already && already.classList.contains('edit-row')) {
      already.remove();
      return;
    }
    closeEditRows();

    // An admin editing another account's instance may only assign that
    // account's own groups; an owner's cache already holds only their own.
    const candidates = lastSecurityGroups.filter((group) => group.account_id === instance.account_id);
    const current = new Set((instance.security_groups || []).map((group) => group.group_id));

    const checklist = document.createElement('div');
    checklist.className = 'checklist';
    const inputs = candidates.map((group) => {
      const label = document.createElement('label');
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.value = group.group_id;
      input.checked = current.has(group.group_id);
      label.append(input, group.group_name);
      checklist.append(label);
      return input;
    });

    const hint = document.createElement('p');
    hint.className = 'muted small wide';
    hint.textContent = candidates.length > 0
      ? 'このアカウントのセキュリティグループから1〜5個選んでください。'
      : 'このアカウントにはセキュリティグループがありません。';

    const save = document.createElement('button');
    save.type = 'submit';
    save.textContent = '保存';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.textContent = 'やめる';
    cancel.addEventListener('click', () => editRow.remove());

    const form = document.createElement('form');
    form.className = 'edit-instance';
    form.append(checklist, hint, save, cancel);
    form.addEventListener('submit', async (submit) => {
      submit.preventDefault();
      const selected = inputs.filter((input) => input.checked).map((input) => input.value);
      if (selected.length < 1 || selected.length > 5) {
        showError(new Error('セキュリティグループは1〜5個選んでください'));
        return;
      }
      try {
        $('error').hidden = true;
        await api('PUT', `/v1/instances/${encodeURIComponent(instance.instance_id)}/security-groups`,
          { security_group_ids: selected });
        editRow.remove();
        await loadInstances();
      } catch (error) {
        showError(error);
      }
    });

    const editRow = document.createElement('tr');
    editRow.className = 'edit-row';
    const td = document.createElement('td');
    td.colSpan = 9;
    td.append(form);
    editRow.append(td);
    row.after(editRow);
  }

  function instanceRow(instance, viewerAccountId, isAdmin) {
    const row = document.createElement('tr');

    const nameCell = document.createElement('td');
    nameCell.append((instance.tags && instance.tags.Name) || '—');
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
      changeGroups.addEventListener('click', () => toggleGroupEditRow(row, instance));
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
    if (isAdmin) {
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.textContent = '編集';
      edit.addEventListener('click', () => toggleEditRow(row, instance));
      actions.append(edit);
    }
    row.append(actions);
    return row;
  }

  // Re-arms itself only while some instance is mid-transition, so there is
  // never more than one timer in flight.
  let instancePollTimer = null;
  function scheduleInstancePoll(instances) {
    if (instancePollTimer) {
      clearTimeout(instancePollTimer);
      instancePollTimer = null;
    }
    if (instances.some((instance) => TRANSIENT_STATES.has(instance.state))) {
      instancePollTimer = setTimeout(loadInstances, 5000);
    }
  }

  async function loadInstances() {
    const wrap = $('instances-wrap');
    const viewerAccountId = wrap.dataset.accountId;
    const isAdmin = wrap.dataset.isAdmin === 'true';
    try {
      const { instances } = await api('GET', '/v1/instances');
      $('instances').replaceChildren(...instances.map((instance) => instanceRow(instance, viewerAccountId, isAdmin)));
      scheduleInstancePoll(instances);
    } catch (error) {
      const row = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 9;
      td.className = 'muted';
      td.textContent = error.message;
      row.append(td);
      $('instances').replaceChildren(row);
      scheduleInstancePoll([]);
    }
  }

  const createInstanceForm = $('create-instance');
  createInstanceForm.querySelector('select[name="preset"]').addEventListener('change', (event) => {
    const preset = presetTypes.get(event.target.value);
    if (!preset) return;
    createInstanceForm.querySelector('input[name="vcpus"]').value = preset.vcpus;
    createInstanceForm.querySelector('input[name="memory_mib"]').value = preset.memory_mib;
    createInstanceForm.querySelector('input[name="memory_min_mib"]').value = preset.memory_min_mib;
  });
  createInstanceForm.querySelector('input[name="ballooning"]').addEventListener('change', (event) => {
    createInstanceForm.querySelector('input[name="memory_min_mib"]').disabled = !event.target.checked;
  });
  createInstanceForm.addEventListener('submit', async (submit) => {
    submit.preventDefault();
    const data = new FormData(createInstanceForm);
    const vcpus = data.get('vcpus');
    const memoryMib = data.get('memory_mib');
    const preset = data.get('preset');
    const body = {
      image_id: data.get('image_id'),
      ballooning: createInstanceForm.querySelector('input[name="ballooning"]').checked,
    };
    if (preset && !vcpus && !memoryMib) body.instance_type = preset;
    if (vcpus) body.vcpus = Number(vcpus);
    if (memoryMib) body.memory_mib = Number(memoryMib);
    const memoryMinMib = data.get('memory_min_mib');
    if (memoryMinMib) body.memory_min_mib = Number(memoryMinMib);
    const rootDiskGib = data.get('root_disk_gib');
    if (rootDiskGib) body.root_disk_gib = Number(rootDiskGib);
    const userData = data.get('user_data');
    if (userData) body.user_data = userData;
    const keyName = data.get('key_name');
    if (keyName) body.key_name = keyName;
    const name = data.get('name');
    if (name) body.tags = { Name: name };
    // Omitted entirely (rather than sent empty) when nothing is checked, so
    // the API falls back to the account's default group.
    const groupIds = data.getAll('security_group_ids');
    if (groupIds.length > 0) body.security_group_ids = groupIds;
    try {
      $('error').hidden = true;
      await api('POST', '/v1/instances', body);
      createInstanceForm.reset();
      createInstanceForm.querySelector('input[name="memory_min_mib"]').disabled =
        !createInstanceForm.querySelector('input[name="ballooning"]').checked;
      await Promise.all([loadInstances(), loadCapacity()]);
    } catch (error) {
      showError(error);
    }
  });

  const adoptForm = $('adopt-instance-form');
  if (adoptForm) {
    adoptForm.addEventListener('submit', async (submit) => {
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
        showError(error);
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
        attach.addEventListener('click', async () => {
          try {
            $('error').hidden = true;
            await api('POST', `/v1/volumes/${encodeURIComponent(volume.volume_id)}/attach`, { instance_id: select.value });
            await Promise.all([loadVolumes(), loadCapacity()]);
          } catch (error) {
            showError(error);
          }
        });
        td.append(select, attach);
      } else {
        const noneNote = document.createElement('span');
        noneNote.className = 'muted small';
        noneNote.textContent = '接続先なし';
        td.append(noneNote);
      }

      const del = document.createElement('button');
      del.type = 'button';
      del.textContent = '削除';
      del.addEventListener('click', async () => {
        const label = (volume.tags && volume.tags.Name) || volume.volume_id;
        if (!confirm(`ボリューム「${label}」を削除します。`)) return;
        try {
          $('error').hidden = true;
          await api('DELETE', `/v1/volumes/${encodeURIComponent(volume.volume_id)}`);
          await Promise.all([loadVolumes(), loadCapacity()]);
        } catch (error) {
          showError(error);
        }
      });
      td.append(del);
    }

    if (volume.state === 'in-use' && volume.attachment && volume.attachment.state === 'attached') {
      const detach = document.createElement('button');
      detach.type = 'button';
      detach.textContent = '切断';
      detach.addEventListener('click', async () => {
        if (!confirm('ゲストでアンマウントしてから切断してください。切断を続けますか？')) return;
        try {
          $('error').hidden = true;
          await api('POST', `/v1/volumes/${encodeURIComponent(volume.volume_id)}/detach`);
          await Promise.all([loadVolumes(), loadCapacity()]);
        } catch (error) {
          showError(error);
        }
      });
      td.append(detach);
    }

    if (volume.state === 'available' || volume.state === 'in-use') {
      const resize = numberField('拡張後 GiB', 'size_gib', volume.size_gib, volume.size_gib + 1);
      const grow = document.createElement('button');
      grow.type = 'button';
      grow.textContent = '拡張';
      grow.addEventListener('click', async () => {
        const size = Number(resize.input.value);
        if (!(size > volume.size_gib)) {
          showError(new Error('拡張後の大きさは現在より大きくしてください'));
          return;
        }
        try {
          $('error').hidden = true;
          await api('PATCH', `/v1/volumes/${encodeURIComponent(volume.volume_id)}`, { size_gib: size });
          await Promise.all([loadVolumes(), loadCapacity()]);
        } catch (error) {
          showError(error);
        }
      });
      td.append(resize.label, grow);
    }
    return td;
  }

  function volumeRow(volume, viewerAccountId, isAdmin, instances) {
    const row = document.createElement('tr');
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

  // Busy whenever a volume itself is transitioning, is mid-resize, or its
  // attachment is mid-attach/detach (attached and detached are the only
  // steady states).
  let volumePollTimer = null;
  function scheduleVolumePoll(volumes) {
    if (volumePollTimer) {
      clearTimeout(volumePollTimer);
      volumePollTimer = null;
    }
    const busy = volumes.some((volume) => VOLUME_TRANSIENT_STATES.has(volume.state) || volume.modification_state
      || (volume.attachment && volume.attachment.state !== 'attached'));
    if (busy) volumePollTimer = setTimeout(loadVolumes, 5000);
  }

  async function loadVolumes() {
    const wrap = $('volumes-wrap');
    const viewerAccountId = wrap.dataset.accountId;
    const isAdmin = wrap.dataset.isAdmin === 'true';
    try {
      const [{ volumes }, { instances }] = await Promise.all([
        api('GET', '/v1/volumes'),
        api('GET', '/v1/instances'),
      ]);
      $('volumes').replaceChildren(...volumes.map((volume) => volumeRow(volume, viewerAccountId, isAdmin, instances)));
      scheduleVolumePoll(volumes);
    } catch (error) {
      const row = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 8;
      td.className = 'muted';
      td.textContent = error.message;
      row.append(td);
      $('volumes').replaceChildren(row);
      scheduleVolumePoll([]);
    }
  }

  $('create-volume').addEventListener('submit', async (submit) => {
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
      showError(error);
    }
  });

  const PROTOCOL_LABELS = { tcp: 'TCP', udp: 'UDP', icmp: 'ICMP', icmpv6: 'ICMPv6', all: 'すべて' };

  function securityRuleTable(groupId, rules, canManage) {
    const table = document.createElement('table');
    const headRow = document.createElement('tr');
    headRow.append(...['プロトコル', 'ポート', '相手', '説明', ''].map((text) => {
      const th = document.createElement('th');
      th.textContent = text;
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
        del.addEventListener('click', async () => {
          if (!confirm('このルールを削除します。')) return;
          try {
            $('error').hidden = true;
            await api('DELETE', `/v1/security-groups/${encodeURIComponent(groupId)}/rules/${encodeURIComponent(rule.rule_id)}`);
            await loadSecurityGroups();
          } catch (error) {
            showError(error);
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
    form.addEventListener('submit', async (submit) => {
      submit.preventDefault();
      const protocol = protoSelect.value;
      const rule = { protocol, cidr: cidrInput.value || '0.0.0.0/0' };
      if (protocol === 'tcp' || protocol === 'udp') {
        const from = Number(fromField.input.value);
        if (!from) {
          showError(new Error('開始ポートを入力してください'));
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
        showError(error);
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
        del.addEventListener('click', async () => {
          if (!confirm(`セキュリティグループ「${group.group_name}」を削除します。`)) return;
          try {
            $('error').hidden = true;
            await api('DELETE', `/v1/security-groups/${encodeURIComponent(group.group_id)}`);
            await loadSecurityGroups();
          } catch (error) {
            showError(error);
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
    } catch (error) {
      lastSecurityGroups = [];
      $('security-groups').replaceChildren(note(error.message));
    }
  }

  $('create-security-group').addEventListener('submit', async (submit) => {
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
      showError(error);
    }
  });

  // GET /v1/limits is readable by every caller (only PUT is admin-only), so
  // the create-volume form's min/max come from here even for non-admins. The
  // form itself (below) only exists in the DOM for admins.
  async function loadLimits() {
    try {
      const data = await api('GET', '/v1/limits');
      const sizeInput = document.querySelector('#create-volume input[name="size_gib"]');
      const bounds = data.limits && data.limits.volume_size_gib;
      if (sizeInput && bounds) {
        sizeInput.min = String(bounds.min);
        sizeInput.max = String(bounds.max);
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
    } catch (error) {
      if ($('limits-status')) $('limits-status').textContent = error.message;
    }
  }

  async function saveLimits(patch) {
    try {
      $('error').hidden = true;
      await api('PUT', '/v1/limits', patch);
      await Promise.all([loadLimits(), loadCapacity()]);
    } catch (error) {
      showError(error);
    }
  }

  if ($('limits')) {
    $('limits').addEventListener('submit', async (submit) => {
      submit.preventDefault();
      const patch = {};
      for (const input of $('limits').querySelectorAll('input[name]')) {
        if (input.value.trim() === '') continue;
        const [group, field] = input.name.split('.');
        patch[group] = patch[group] || {};
        patch[group][field] = Number(input.value);
      }
      await saveLimits(patch);
    });
    $('reset-limits').addEventListener('click', async () => {
      if (!confirm('上限をすべて既定値へ戻します。')) return;
      await saveLimits({});
    });
  }

  const refresh = () => Promise.all([
    loadKeys(), loadEvents(), loadCapacity(), loadLimits(), loadInstances(), loadImages(), loadKeyPairs(),
    loadVolumes(), loadSecurityGroups(),
  ]);

  $('create-key').addEventListener('submit', async (submit) => {
    submit.preventDefault();
    const form = new FormData(submit.target);
    const body = { description: form.get('description') };
    if (form.get('expires_in_days')) body.expires_in_days = Number(form.get('expires_in_days'));
    try {
      $('error').hidden = true;
      const created = await api('POST', '/v1/access-keys', body);
      $('new-secret-value').textContent = created.secret_access_key;
      $('new-secret-usage').textContent =
        `export SHAKECLOUD_ACCESS_KEY='${created.secret_access_key}'\n` +
        `curl -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" ${location.origin}/v1/caller-identity`;
      $('new-secret').hidden = false;
      submit.target.reset();
      await refresh();
    } catch (error) {
      showError(error);
    }
  });

  $('import-key-pair').addEventListener('submit', async (submit) => {
    submit.preventDefault();
    const form = new FormData(submit.target);
    const body = { key_name: form.get('key_name'), public_key: form.get('public_key') };
    try {
      $('error').hidden = true;
      await api('POST', '/v1/key-pairs', body);
      submit.target.reset();
      await loadKeyPairs();
    } catch (error) {
      showError(error);
    }
  });

  // Uses XMLHttpRequest instead of the shared api() helper because it needs
  // upload progress events, which fetch() cannot provide. The request/error
  // shape mirrors api() by hand: parse the same {error:{code,message}} body,
  // and bounce to / on 401 like api() does.
  $('upload-image').addEventListener('submit', (submit) => {
    submit.preventDefault();
    const form = submit.target;
    const file = form.elements.file.files[0];
    if (!file) return;
    const data = new FormData();
    data.append('name', form.elements.name.value);
    data.append('file', file);

    const progress = $('upload-progress');
    const status = $('upload-status');
    $('error').hidden = true;
    progress.value = 0;
    progress.hidden = false;
    status.textContent = 'アップロード中… 0%';

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/v1/images');
    xhr.withCredentials = true;
    // No xhr.timeout: uploads of large images can legitimately take minutes.
    xhr.upload.addEventListener('progress', (event) => {
      if (!event.lengthComputable) return;
      const percent = Math.round((event.loaded / event.total) * 100);
      progress.value = percent;
      status.textContent = `アップロード中… ${percent}%`;
    });
    xhr.addEventListener('load', async () => {
      progress.hidden = true;
      if (xhr.status === 401) {
        location.href = '/';
        return;
      }
      if (xhr.status === 201) {
        status.textContent = 'アップロードしました。';
        form.reset();
        await Promise.all([loadImages(), loadCapacity()]);
        return;
      }
      status.textContent = '';
      let message = `アップロードに失敗しました（${xhr.status}）`;
      try {
        const body = JSON.parse(xhr.responseText);
        message = `${body.error.message}（${body.error.code}、request ${body.request_id}）`;
      } catch (error) {
        // Response body was not the usual JSON error shape; keep the generic message.
      }
      showError(new Error(message));
    });
    xhr.addEventListener('error', () => {
      progress.hidden = true;
      status.textContent = '';
      showError(new Error('アップロード中に通信エラーが発生しました'));
    });
    xhr.send(data);
  });

  $('dismiss-secret').addEventListener('click', () => {
    $('new-secret-value').textContent = '';
    $('new-secret-usage').textContent = '';
    $('new-secret').hidden = true;
  });

  $('logout').addEventListener('click', async () => {
    try {
      await api('POST', '/auth/logout');
    } finally {
      location.href = '/';
    }
  });

  loadInstanceTypes();
  refresh().catch(showError);
})();
