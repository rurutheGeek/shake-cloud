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

  const refresh = () => Promise.all([loadKeys(), loadEvents(), loadCapacity(), loadLimits()]);

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

  refresh().catch(showError);
})();
