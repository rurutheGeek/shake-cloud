'use strict';
// Phase 1 portal. Uses the same JSON API as Terraform, authenticated by the
// session cookie. The self-service portal replaces it in Phase 5.
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
        + ` ・ ディスク ${capacity.cloud.root_disk_gib} GiB`));
      parts.push(note(`あなたの利用: ${capacity.account.instances}台 ・ ${capacity.account.vcpus} vCPU`
        + ` ・ メモリ ${mib(capacity.account.memory_mib)} ・ ディスク ${capacity.account.root_disk_gib} GiB`));
      $('capacity').replaceChildren(...parts);

      if (capacity.accounts) {
        $('account-usage').replaceChildren(...capacity.accounts.map((entry) => {
          const row = document.createElement('tr');
          row.append(cell(entry.account_id), cell(entry.username), cell(entry.instances),
            cell(entry.vcpus), cell(mib(entry.memory_mib)), cell(entry.root_disk_gib + ' GiB'));
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

  async function loadImages() {
    const select = document.querySelector('#create-instance select[name="image_id"]');
    try {
      const { images } = await api('GET', '/v1/images');
      select.replaceChildren(...images.map((image) => {
        const option = document.createElement('option');
        option.value = image.image_id;
        option.textContent = image.name;
        return option;
      }));
    } catch (error) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = '取得できません';
      select.replaceChildren(option);
    }
  }

  // Filled in by loadInstanceTypes and read by the preset <select>'s change
  // handler, so picking a preset can fill in the vCPU/memory/floor inputs.
  let presetTypes = new Map();

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
    td.colSpan = 8;
    td.append(form);
    editRow.append(td);
    row.after(editRow);
  }

  function instanceRow(instance, viewerAccountId, isAdmin) {
    const row = document.createElement('tr');

    const nameCell = document.createElement('td');
    nameCell.append((instance.tags && instance.tags.Name) || '—');
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

    row.append(
      nameCell,
      cell(instance.owner_username || instance.account_id),
      stateCell,
      cell(instance.private_ip_address || '—'),
      cell(instance.image_name || instance.image_id),
      configCell,
      cell(instance.root_disk_gib + ' GiB'),
    );

    const actions = document.createElement('td');
    if (instance.account_id === viewerAccountId || isAdmin) {
      const id = encodeURIComponent(instance.instance_id);
      actions.append(
        powerButton('起動', `/v1/instances/${id}/start`, instance.state === 'stopped'),
        powerButton('停止', `/v1/instances/${id}/stop`, instance.state === 'running'),
        powerButton('再起動', `/v1/instances/${id}/reboot`, instance.state === 'running'),
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
      td.colSpan = 8;
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
    const name = data.get('name');
    if (name) body.tags = { Name: name };
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

  // The form shows an administrator's overrides as values and the deployment's
  // defaults as placeholders, so an empty box always means "use the default".
  async function loadLimits() {
    if (!$('limits')) return;
    try {
      const data = await api('GET', '/v1/limits');
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
      $('limits-status').textContent = error.message;
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

  const refresh = () => Promise.all([loadKeys(), loadEvents(), loadCapacity(), loadLimits(), loadInstances()]);

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

  loadImages();
  loadInstanceTypes();
  refresh().catch(showError);
})();
